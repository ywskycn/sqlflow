# Design Doc: Model Definition and Model Zoo

## Introduction

SQLFlow extends SQL syntax to allow SQL programmers, a.k.a., analysts, to invoke models defined by Python programmers, a.k.a., data scientists.  For each deployment of SQLFlow service, we refer to the collection of **model definitions** accessible by analysts as a **model zoo**.  A model zoo contains not only the model definitions but also the trained model parameters, as well as the hyperparameters and other information, which are necessary when we use the model for prediction and other analytics jobs.

This document is about how to define models and how to build a model zoo.

## Background

The following example SQL statement shows the syntax for training a model.

```sql
SELECT * FROM employee WHERE onboard_year < 2019
TO TRAIN MyDNNRegressor
WITH hidden_units=[10,50,5], lr=0.01
COLUMN gender, scale(age, 0, 1), bucketize(address, 100) 
LABEL salary 
INTO my_first_model;
```

The identifier `MyDNNRegressor` names a Python class derived from `tf.keras.Model`.  The `WITH` clause provides hyperparameters required by the constructor of `MyDNNRegressor`  and the training process. The `COLUMN` clause specifies how to convert the SELECT result, a table, into model inputs in the form of tensors. `LABEL` identifies the field used as the label, in the case of supervised learning.  The training process saves all the above information, plus the estimated model parameters, under the name `my_first_model`.

The following example fills in the column `predicted_salary` of the table `employee` for rows that represent employees recruited in and after 2019.

```sql
SELECT * FROM employee WHERE onboard_year >= 2019 
TO PREDICT employee.predicted_salary
USING my_first_model;
```

Users don't have to write the `COLUMN` clause in the above example, as SQLFlow reuses the one in the training statement.

## Concepts

The above training and prediction example reveals some concepts related to models.

1. A **dataset** is defined and generated by a SQL SELECT statement. For example, `SELECT * FROM employee WHERE onboard_year < 2019`.

1. A **data source** is a table, for example, `employee`.  Please be aware that we can cache and reuse a dataset until its data sources are changed.

1. A **model definition**, for example, `MyDNNRegressor`, is a Python class or other kinds of code that specify a model.

1. The SQL data to model inputs conversion, or **data conversion**, is the COLUMN and optionally LABEL clauses.

1. Hyperparameters
   1. **Model hyperparameters** are some key-value pairs specified in the WITH clause. They are arguments to the constructor of the model definition.
   1. **Training hyperparameters** appear in WITH, as model constructors do. They affect the training process.
   1. **Data conversion hyperparameters** appear in COLUMN and optionally LABEL. For example, the scale range and bucket size in the first example.

1. A **trained model** consists of all the above concepts and the estimated model parameters.

In SQLFlow SQL grammar, the identifiers after `TRAIN`, `USING` and `INTO` have different meanings:

1. `TRAIN IDENT`: `IDENT` is the name of a model definition.
1. `USING IDENT`: `IDENT` is the `model ID` refering to a **trained model**, please refer to the below sections for the definition of `model ID`.
1. `INTO IDENT`: `IDENT` is the `model ID` refering to a **trained model**.

## The Design

### Versioning and Releasing

A key to this design is the representation of the above concepts.  It is not a straightforward solution. For example, in prior work and previous discussions, engineers proposed to represent each model definition by a Python source code file hosted on an FTP service and downloaded when some users file a model training statement. This intuitive proposal could lead to inconsistencies. Suppose that an analyst trained a model using the definition in `my_dnn_regressor.py` and got `my_first_model`; soon after that, a data scientist changed `my_dnn_regressor.py` and the analyst re-trained the model into `my_second_model` with slightly modified hyperparameter settings. The analyst might expect that both models share the same definition; however, they don't, and worse than that, there is no mechanism to remind the change of the model definition to the analyst.

Such design flaw roots from the ignoring of the fact that model definitions are code that has versions. Another important aspect is that we often build the source code into some release-ready form.  Once we noticed these facts, we can use version management tools like Git and release engineering tools like Docker.  Here follows our proposal.

1. A collection of model definitions is a Git repository of source files. 
1. To describe dependencies, we require a Dockerfile at the root directory of the repository.
1. To release a repository, we checkout the specific version and run `docker run` with the Dockerfile.

### Submitter Programs

For a SELECT program using the SQLFlow syntax extension, the SQLFlow server converts it into a *submitter* program, usually in Python.

Consider the training statement at the beginning of this document. Suppose that the Python class `MyDNNRegressor` is in source file `my_dnn_regressor.py` in the repository https://github.com/a_data_scientist/regressors, which builds into Docker image `a_data_scientist/regressors`.  Let us also assume that the submitter program is `/var/sqlflow/submitters/an_analyst/my_first_model.py`.  SQLFlow can run the submitter using the Docker image as follows:

```bash
docker run --rm -it \
  -v /var/sqlflow/submitters:/submitters \
  a_data_scientist/regressors \
    python /submitters/an_analyst/my_first_model.py
```

To submit an ElasticDL training job, we need the following actions:

1. The SQLFlow server invokes `codegen_elasticdl.go` to generates the submitter program `my_first_model.py`.
1. `my_first_model.py` calls the ElasticDL client API to submit a job.
1. The SQLFlow server then runs `my_first_model.py` in a Docker container (if SQLFlow service is not running in a Kubernetes cluster), or a Pod, which has ElasticDL client library installed.
1. As this container needs to contain ElasticDL and the model definition, all model Docker images should derive from our base image which installs ElasticDL by default:

```
FROM sqlflow/sqlflow_model_base
...
```

If we run SQLFlow in a Docker container, to allow it to run another Docker container, we must enable the Docker-in-Docker feature, say, following [this blog post](https://itnext.io/docker-in-docker-521958d34efd).  Suppose that the SQLFlow server runs in a Kubernetes cluster, where we cannot enable Docker-in-Docker. In such a case, we can make the SQLFlow server call Kubernetes API to run a Pod that executes the above `docker run` command line.

The training submitter program `my_first_model.py`, running in the model definition Docker container, should be able to submit a (distributed) training job to a preconfigured cluster.  Once the job completes, the submitter program adds, or edits, a row in a **model zoo table**.

### Model Zoo Data Schema

The model zoo table is in a database deployed as part of the SQLFlow service. This database might not be the one that holds data sources.  The only requirement of the model zoo table is to have a particular data schema that contains at least the following fields.

1. model ID (key), specified by the INTO clause, or `an_analyst/my_first_model` in the above example.
1. Docker image ID, the Docker commit ID of the image `a_data_scientist/regressors` in the above example.
1. submitter program, the source code of the submitter program, `my_first_model.py` in the above example, or its MD5 hash.
1. data converter, the COLUMN and LABEL clauses.
1. model parameter file path, the path to the trained model parameters on the distributed filesystem of the cluster.

It is necessary to have the model ID so users can refer to the trained model when they want to use it.  Suppose that the user typed the prediction SQL statement at the beginning of this document. SQLFlow server will convert it into a submitter program and run it with the Docker image used to train the model. Therefore, the Docker image ID is also required. The model parameter path allows the prediction submitter program to locate and load the trained models.  The data converter helps the prediction submitter to use the conversion rules consistent with the ones used when training.

It is necessary to record the content or the MD5 hash of the training submitter program in the model zoo table for experiment management. Please be aware that the training submitter encodes all three categories of hyperparameters, as listed in the above sections.  Suppose that the analyst re-trains the model with different hyperparameter settings, the training submitter changes accordingly, and SQLFlow should be able to remind the analyst to either uses a new model ID or overwrites the existing row in the model zoo table.

### Model Sharing

After all, what is a model zoo? A model zoo refers to all the model definitions and trained models accessible by a deployment of SQLFlow.  It contains one or more model definition Docker images and the source code repositories that build the images.  It also includes the model zoo table configured to work with all submitter programs generated by the deployment.

Within a deployment, it is straightforward to share a trained model.  If the analyst, `an_analyst`, in the above example wants to use her own trained model `my_first_model` for prediction, she could use the short name `my_first_model`.

```sql
SELECT ... TO PREDICT ... USING my_first_model
```

If another analyst wants to use the trained model, he would need to use the full name as `an_analyst/my_first_model`.

```sql
SELECT ... TO PREDICT ... USING an_analyst/my_first_model
```

There could be more than one model definitions in each model's Docker image. We need to be able to find out which model definition is used to train current saved model. Also if we only want to reuse the model definition to train a new model we need to know the model definition class name, so that we can pass it to the `TRAIN` clause.

To list all trained models of one user, you can do:

```sql
SQLFLOW LIST an_analyst
```

This should output a table showing the saved models and which model definition it was using.

```
|  saved model    |   model def    |
| my_first_model  | MyDNNRegressor |
| my_second_model | MyDNNRegressor |
```

Within **any** deployment that have internet access, to list published models:

```sql
SQLFLOW LIST [models.sqlflow.com/an_analyst]
```

Display model definitions and documentation of the published model:

```
SQLFLOW DESCRIBE model.sqlflow.com/an_analyst/my_first_model;
| available model defs |
| MyDNNRegressor       |
| MyDNNClassifier      |

SQLFLOW DESCRIBE model.sqlflow.com/an_analyst/my_first_model.MyDNNRegressor;

Documatation for my_first_model.MyDNNRegressor
...
...
```

Use a published model make some predictions on new data:

```sql
SELECT ... TO PREDICT employee.predicted_salary USING model.sqlflow.com/an_analyst/my_first_model
```

### Model Publication

Publishing a model definition, we hope all users of all SQLFlow deployments can train the model using their datasets. To achieve this goal, data scientists need to set up a continuous deployment system to automatically build their model definition repositories into Docker images and push to a public Docker registry like DockerHub.com.  In the above example, the Docker image `a_data_scientist/regressors` is one hosted on DockerHub.com.

It requires more steps to publish a trained model. We need a public registry like DockerHub.com, but hosts rows from the model zoo table and corresponding model parameters.  We propose the following extended SQL syntax for analysts `an_analyst` to publish her trained model.

```sql
SQLFLOW PUBLISH my_first_model
    [TO https://models.sqlflow.com/user_name]
```

This statement uploads the model parameters and other information to the registry service, which defaults to https://models.sqlflow.com, and under the account `user_name`, which defaults to `an_analyst` in the above example.

Then, another analyst should be able to use the trained model by referring to it in its full name.

```sql
SELECT ... TO PREDICT employee.predicted_salary USING model.sqlflow.com/an_analyst/my_first_model
```

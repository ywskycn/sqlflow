# Copyright 2019 The SQLFlow Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from sqlflow_submitter.tensorflow.estimator_train_pred import datasource, select, validate_select, feature_column_names, feature_column_code, feature_metas, label_meta
from sqlflow_submitter.tensorflow.train import train
from sqlflow_submitter.tensorflow.predict import pred

if __name__ == "__main__":
    train(is_keras_model=True,
        datasource=datasource,
        estimator="sqlflow_models.DNNClassifier",
        select=select,
        validate_select=validate_select,
        feature_column_code=feature_column_code,
        feature_column_names=feature_column_names,
        feature_metas=feature_metas,
        label_meta=label_meta,
        model_params={"n_classes": 3, "hidden_units":[10,20]},
        save="mymodel_keras",
        batch_size=1,
        epochs=1,
        verbose=0)
    pred(is_keras_model=True,
        datasource=datasource,
        estimator="sqlflow_models.DNNClassifier",
        select=select,
        result_table="iris.predict",
        feature_column_code=feature_column_code,
        feature_column_names=feature_column_names,
        feature_metas=feature_metas,
        label_meta=label_meta,
        model_params={"n_classes": 3, "hidden_units":[10,20]},
        save="mymodel_keras",
        batch_size=1)


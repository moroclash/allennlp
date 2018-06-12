# pylint: disable=no-self-use,invalid-name,line-too-long,no-member

import json
import os
import pathlib
import sys

from allennlp.common.testing import AllenNlpTestCase
from allennlp.service import config_explorer
from allennlp.service.config_explorer import make_app, _HTML


class TestConfigExplorer(AllenNlpTestCase):

    def setUp(self):
        super().setUp()
        app = make_app()
        app.testing = True
        self.client = app.test_client()

    def test_html(self):
        """
        The pip-installed version of allennlp (currently) requires the config explorer HTML
        to be hardcoded into the server file. But when iterating on it, it's easier to use the
        /debug/ endpoint, which points at `config_explorer.html`, so that you don't have to
        restart the server every time you make a change.

        This test just ensures that the two HTML versions are identical, to prevent you from
        making a change to the standalone HTML but forgetting to change the corresponding
        server HTML. There is certainly a better way to handle this.
        """
        config_explorer_dir = pathlib.Path(config_explorer.__file__).parent
        config_explorer_file = config_explorer_dir / 'config_explorer.html'

        if not config_explorer_file.exists():
            print("standalone config_explorer.html does not exist, skipping test")
        else:
            with open(config_explorer_file) as f:
                html = f.read()

            assert html.strip() == _HTML.strip()

    def test_app(self):
        response = self.client.get('/')
        html = response.get_data().decode('utf-8')

        assert "AllenNLP Configuration Wizard" in html

    def test_api(self):
        response = self.client.get('/api/')
        data = json.loads(response.get_data())

        assert data["className"] == ""

        items = data["config"]['items']

        assert items[0] == {
                "name": "dataset_reader",
                "configurable": True,
                "comment": "specify your dataset reader here",
                "annotation": {'origin': "allennlp.data.dataset_readers.dataset_reader.DatasetReader"}
        }


    def test_choices(self):
        response = self.client.get('/api/?class=allennlp.data.dataset_readers.dataset_reader.DatasetReader')
        data = json.loads(response.get_data())

        assert "allennlp.data.dataset_readers.reading_comprehension.squad.SquadReader" in data["choices"]

    def test_subclass(self):
        response = self.client.get('/api/?class=allennlp.data.dataset_readers.semantic_role_labeling.SrlReader')
        data = json.loads(response.get_data())

        config = data['config']
        items = config['items']
        assert config['type'] == 'srl'
        assert items[0]["name"] == "token_indexers"

    def test_torch_class(self):
        response = self.client.get('/api/?class=torch.optim.rmsprop.RMSprop')
        data = json.loads(response.get_data())
        config = data['config']
        items = config['items']

        assert config["type"] == "rmsprop"
        assert any(item["name"] == "lr" for item in items)

    def test_rnn_hack(self):
        response = self.client.get('/api/?class=torch.nn.modules.rnn.LSTM')
        data = json.loads(response.get_data())
        config = data['config']
        items = config['items']

        assert config["type"] == "lstm"
        assert any(item["name"] == "batch_first" for item in items)

    def test_initializers(self):
        response = self.client.get('/api/?class=allennlp.nn.initializers.Initializer')
        data = json.loads(response.get_data())

        assert 'torch.nn.init.constant_' in data["choices"]
        assert 'allennlp.nn.initializers.block_orthogonal' in data["choices"]

        response = self.client.get('/api/?class=torch.nn.init.uniform_')
        data = json.loads(response.get_data())
        config = data['config']
        items = config['items']

        assert config["type"] == "uniform"
        assert any(item["name"] == "a" for item in items)

    def test_regularizers(self):
        response = self.client.get('/api/?class=allennlp.nn.regularizers.regularizer.Regularizer')
        data = json.loads(response.get_data())

        assert 'allennlp.nn.regularizers.regularizers.L1Regularizer' in data["choices"]

        response = self.client.get('/api/?class=allennlp.nn.regularizers.regularizers.L1Regularizer')
        data = json.loads(response.get_data())
        config = data['config']
        items = config['items']

        assert config["type"] == "l1"
        assert any(item["name"] == "alpha" for item in items)

    def test_other_modules(self):
        # Create a new package in a temporary dir
        packagedir = self.TEST_DIR / 'configexplorer'
        packagedir.mkdir()  # pylint: disable=no-member
        (packagedir / '__init__.py').touch()  # pylint: disable=no-member

        # And add that directory to the path
        sys.path.insert(0, str(self.TEST_DIR))

        # Write out a duplicate predictor there, but registered under a different name.
        from allennlp.predictors import bidaf
        with open(bidaf.__file__) as f:
            code = f.read().replace("""@Predictor.register('machine-comprehension')""",
                                    """@Predictor.register('config-explorer-predictor')""")

        with open(os.path.join(packagedir, 'predictor.py'), 'w') as f:
            f.write(code)

        # Without specifying modules to load, it shouldn't be there
        app = make_app()
        app.testing = True
        client = app.test_client()
        response = client.get('/api/?class=allennlp.predictors.predictor.Predictor')
        data = json.loads(response.get_data())
        assert "allennlp.predictors.bidaf.BidafPredictor" in data["choices"]
        assert "configexplorer.predictor.BidafPredictor" not in data["choices"]

        # With specifying extra modules, it should be there.
        app = make_app(['configexplorer'])
        app.testing = True
        client = app.test_client()
        response = client.get('/api/?class=allennlp.predictors.predictor.Predictor')
        data = json.loads(response.get_data())
        assert "allennlp.predictors.bidaf.BidafPredictor" in data["choices"]
        assert "configexplorer.predictor.BidafPredictor" in data["choices"]

        sys.path.remove(str(self.TEST_DIR))
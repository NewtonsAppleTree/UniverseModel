"""Real-source loading, partition ownership, train-only fitting and independent classification arithmetic."""

from dataclasses import replace
from hashlib import sha256
from math import exp,log,ulp
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from configuration.resolution.dataclass_config import load_config
from contracts.workload.classification import ClassificationData
from workloads.datasets.tabular import load_classification
from workloads.graphs.retrieval import fit_retrieval,retrieval_attention,select_retrieval_scale,stratified_split
from workloads.profiles.retrieval import RetrievalProfile
from workloads.reference.attention import reference_attention
from workloads.reference.classification import classification_gate,classification_metrics


ROOT = Path(__file__).resolve().parents[2]  # Source data is local and hashed; tests never access a network.


# A tiny dataset makes fitted statistics, held-out ownership and RBF probabilities analytically checkable.
def tiny_data():
    return ClassificationData(features=((0.,),(1.,),(2.,),(4.,),(5.,),(6.,)),labels=(0,0,0,1,1,1),
                              feature_names=('x',),class_names=('a','b'),source_sha256='a'*64)


# These tests establish protocol/numeric behavior, not broad model quality or service representativeness.
class RetrievalTests(unittest.TestCase):
    # Preserve original source discrepancies and complete raw-byte identity instead of silently substituting another Iris copy.
    def test_real_dataset(self):
        profile = load_config(RetrievalProfile,ROOT/'config/experiments/retrieval_quality.json')
        data = load_classification(profile.source,ROOT/'config/workloads')
        self.assertEqual((len(data.features),len(data.features[0])),(150,4))
        self.assertEqual([data.labels.count(i) for i in range(3)],[50]*3)
        self.assertEqual(data.source_sha256,'6f608b71a7317216319b4d27b4d9bc84e6abd734eda7872b71a458569e2656c0')
        self.assertEqual(data.features[34],(4.9,3.1,1.5,0.1))
        self.assertIn('CC BY 4.0',profile.source.usage_terms)

    # Every row belongs to exactly one split, class quotas are explicit and hash ordering is reproducible.
    def test_split_and_state_guards(self):
        data = tiny_data()
        split = stratified_split(data,seed=7,train_per_class=1,validation_per_class=1)
        self.assertEqual(split,stratified_split(data,seed=7,train_per_class=1,validation_per_class=1))
        self.assertEqual(set((*split.train,*split.validation,*split.test)),set(range(6)))
        self.assertEqual((len(split.train),len(split.validation),len(split.test)),(2,2,2))
        for changes in ({'train':split.test},{'seed':True},{'data_identity':'bad'}):
            with self.assertRaises(ValueError):
                replace(split,**changes)
        with self.assertRaises(ValueError):
            stratified_split(data,seed=0,train_per_class=2,validation_per_class=1)
        with self.assertRaisesRegex(ValueError,'match'):
            fit_retrieval(replace(data,source_sha256='b'*64),split)

    # Test examples can change arbitrarily without changing fitted means/scales, support or validation-selected scale.
    def test_no_test_data_leakage(self):
        data = tiny_data()
        split = stratified_split(data,seed=7,train_per_class=1,validation_per_class=1)
        original = fit_retrieval(data,split)
        altered = tuple((1000.,) if i in split.test else row for i,row in enumerate(data.features))
        labels = tuple(1-y if i in split.test else y for i,y in enumerate(data.labels))
        changed = replace(data,features=altered,labels=labels)
        later = fit_retrieval(changed,replace(split,data_identity=changed.identity_hash))
        self.assertEqual((original.means,original.scales,original.support,original.labels),(later.means,later.scales,later.support,later.labels))
        a = select_retrieval_scale(original,data,(.25,1.,4.))
        b = select_retrieval_scale(later,changed,(.25,1.,4.))
        self.assertEqual(a,b)

    # Direct exp(-scale*distance²) is independent of the Q/K polynomial identity used by the task producer.
    def test_rbf_attention_identity_and_rounding(self):
        data = tiny_data()
        state = fit_retrieval(data,stratified_split(data,seed=3,train_per_class=1,validation_per_class=1))
        query = ((2.,),)
        spec,inputs = retrieval_attention(state,query,scale=2.)
        x = (2.-state.means[0])/state.scales[0]
        weights = [exp(-2*(x-z[0])**2) for z in state.support]
        total = sum(weights)
        expected = tuple(sum(w for w,y in zip(weights,state.labels) if y==c)/total for c in range(2))
        actual = reference_attention(spec,inputs).output
        for a,b in zip(actual,expected):
            self.assertAlmostEqual(a,b,delta=1e-13)
        coarse,coarse_input = retrieval_attention(state,query,scale=2.,key_decimals=-2)
        self.assertEqual(reference_attention(coarse,coarse_input).output,(.5,.5))
        with self.assertRaises(ValueError):
            retrieval_attention(state,query,scale=2.,key_decimals=True)

    # Metrics use explicit row-major probabilities, natural-log clipping and deterministic first-class ties.
    def test_metrics_and_exact_gate(self):
        metrics = classification_metrics((.75,.25,.5,.5,0.,1.),(0,1,0),2)
        self.assertEqual((metrics.correct,metrics.confusion,metrics.predictions,metrics.clipped_samples),(1,((1,1),(1,0)),(0,0,1),1))
        self.assertAlmostEqual(metrics.mean_log_loss,(-log(.75)-log(.5)-log(1e-15))/3)
        base = classification_metrics((1.,0.)*20,(0,)*20,2)
        candidate = classification_metrics((1.,0.)*19+(0.,1.),(0,)*20,2)
        self.assertEqual(classification_gate(candidate,base,minimum_accuracy=.95,maximum_accuracy_drop=.05),(True,-.05))
        self.assertFalse(classification_gate(candidate,base,minimum_accuracy=.96,maximum_accuracy_drop=.05)[0])
        for probabilities in ((.2,.2),(-.1,1.1),(float('nan'),1.)):
            with self.assertRaises(ValueError):
                classification_metrics(probabilities,(0,),2)

    # Binary64 endpoint roundoff is tolerated without normalizing predictions or producing negative log loss.
    def test_probability_endpoint_roundoff(self):
        original = (1.+ulp(1.),-ulp(1.))
        metrics = classification_metrics(original,(0,),2)
        self.assertEqual((metrics.accuracy,metrics.mean_log_loss,metrics.predictions),(1.,0.,(0,)))
        self.assertEqual(original,(1.+ulp(1.),-ulp(1.)))
        self.assertEqual(classification_metrics(original,(1,),2).clipped_samples,1)
        for invalid in ((1.+2e-9,-2e-9),(1.+.8e-9,.8e-9),(float('inf'),0.)):
            with self.assertRaises(ValueError):
                classification_metrics(invalid,(0,),2)

    # Hash identity, parser domain, path containment and budgets are enforced before source data can enter an experiment.
    def test_dataset_failure_boundaries(self):
        source = load_config(RetrievalProfile,ROOT/'config/experiments/retrieval_quality.json').source
        for changes in ({'relative_path':'../iris.data'},{'sha256':'x'*64},{'feature_names':('x','x')}):
            with self.assertRaises(ValueError):
                replace(source,**changes)
        with self.assertRaisesRegex(ValueError,'max_samples'):
            load_classification(source,ROOT/'config/workloads',max_samples=1)
        with self.assertRaisesRegex(ValueError,'size/SHA256'):
            load_classification(source,ROOT/'config/workloads',max_file_bytes=1)
        with TemporaryDirectory() as root:
            for raw in (b'"unterminated',b'NaN,1,2,3,Iris-setosa',b'1,2,3,4,unknown',b'1,2,Iris-setosa'):
                path = Path(root)/'data.csv'
                path.write_bytes(raw)
                manifest = replace(source,relative_path='data.csv',sha256=sha256(raw).hexdigest())
                with self.assertRaises(ValueError):
                    load_classification(manifest,root)

    # Nested arrays are immutable and semantic changes cannot reuse the original observation identity.
    def test_data_ownership_and_profile_guards(self):
        rows = [[0.],[1.]]
        data = ClassificationData(features=rows,labels=[0,1],feature_names=['x'],class_names=['a','b'],source_sha256='a'*64)
        rows[0][0] = 5.
        self.assertEqual(data.features[0],(0.,))
        profile = load_config(RetrievalProfile,ROOT/'config/experiments/retrieval_quality.json')
        for changes in ({'seeds':(0,0)},{'variants':profile.variants[1:]},{'scale_candidates':(1.,1.)},{'maximum_accuracy_drop':True}):
            with self.assertRaises(ValueError):
                replace(profile,**changes)


if __name__=='__main__':
    unittest.main()

"""Explicit finite-set classification metrics; reporting a score is not evidence of population generalization."""

from dataclasses import dataclass
from fractions import Fraction
from math import fsum, isfinite, log

from contracts.workload.attention import attention_buffer
from contracts.workload.linear import positive_int


PROBABILITY_TOLERANCE = 1e-9  # Absolute binary64 endpoint/row-sum tolerance [1]; raw predictions are never renormalized.


# Confusion rows are true labels and columns predicted labels; ties select the first declared class.
@dataclass(frozen=True, slots=True)
class ClassificationMetrics:
    samples: int  # Number of evaluated held-out samples [sample].
    correct: int  # Correct argmax labels [sample].
    accuracy: float  # correct/samples [1].
    mean_log_loss: float  # -mean(log(min(1,max(p_true,probability_floor)))) [nat/sample]; upper clamp removes endpoint roundoff.
    probability_floor: float  # Explicit log-loss clipping threshold [1], not a prediction modification.
    clipped_samples: int  # True-class probabilities clipped for log reporting [sample].
    confusion: tuple[tuple[int, ...], ...]  # [true,predicted] sample counts.
    predictions: tuple[int, ...]  # Argmax output class for each input sample.


# Allow endpoint/row-sum roundoff within PROBABILITY_TOLERANCE; raw argmax is unchanged and only log reporting clamps.
def classification_metrics(probabilities: tuple[float, ...], labels: tuple[int, ...], classes: int, *,
                           probability_floor: float = 1e-15) -> ClassificationMetrics:
    positive_int('classes',classes)
    if classes<2 or not isinstance(labels,(tuple,list)) or not labels or any(type(y) is not int or not 0<=y<classes for y in labels):
        raise ValueError('invalid classification truth/classes')
    values = attention_buffer('probabilities',probabilities)
    if len(values)!=len(labels)*classes or any(v < -PROBABILITY_TOLERANCE or v > 1+PROBABILITY_TOLERANCE for v in values):
        raise ValueError('classification probability shape/domain mismatch')
    if type(probability_floor) not in (float,int) or not isfinite(probability_floor) or not 0<probability_floor<1:
        raise ValueError('probability_floor must be finite in (0,1)')
    confusion = [[0]*classes for _ in range(classes)]
    predictions,loss,clipped = [],0.0,0
    for i,label in enumerate(labels):
        row = values[i*classes:(i+1)*classes]
        if abs(fsum(row)-1)>PROBABILITY_TOLERANCE:
            raise ValueError('classification probability row must sum to one')
        prediction = max(range(classes),key=lambda j:row[j])
        predictions.append(prediction)
        confusion[label][prediction] += 1
        clipped += row[label]<probability_floor
        loss -= log(min(1.0,max(row[label],probability_floor)))
    correct = sum(label==prediction for label,prediction in zip(labels,predictions))
    return ClassificationMetrics(len(labels),correct,correct/len(labels),loss/len(labels),float(probability_floor),clipped,
                                 tuple(tuple(row) for row in confusion),tuple(predictions))


# Compare exact sample-count ratios against decimal threshold values, avoiding binary64 boundary artifacts.
def classification_gate(actual: ClassificationMetrics, baseline: ClassificationMetrics, *,
                         minimum_accuracy: float, maximum_accuracy_drop: float) -> tuple[bool, float]:
    for value in (minimum_accuracy,maximum_accuracy_drop):
        if type(value) not in (float,int) or not isfinite(value) or not 0<=value<=1:
            raise ValueError('quality thresholds must be finite in [0,1]')
    if actual.samples!=baseline.samples or actual.samples<=0:
        raise ValueError('quality comparison needs the same nonempty test set')
    accuracy = Fraction(actual.correct,actual.samples)
    delta = accuracy-Fraction(baseline.correct,baseline.samples)
    passed = accuracy>=Fraction(str(minimum_accuracy)) and delta>=-Fraction(str(maximum_accuracy_drop))
    return passed,float(delta)

# Evaluation protocol

`evaluation/protocol.json` is versioned before the held-out run. Development uses
seeds 17 and 29. The first held-out evaluation uses seeds 103, 211, 307, 419, and
523 in each of three families, with two local-model attempts per variation:
30 planned attempts on 15 scenarios. Each contains 12 valid business events;
fault injection changes the delivery stream.

The model receives the same observations and action catalog as the runbook.
Each action starts on its own branch copied from the identical captured incident.
The primary outcome requires every independent business invariant to pass.
Model errors, timeouts, denied actions, abstention, and incomplete recovery all
remain in the denominator. Abstention is separately reported; it is not recovery.

Report scenario-family results, per-attempt outcomes, local inference time, and
action execution time. Repeated attempts on one variation are correlated; do not
interpret 30 attempts as 30 independent incidents. Synthetic recovery does not
measure customer impact, real dollars saved, or incident response at scale.

The deterministic baseline is simple and intentionally competitive. It need not
be beaten to make the lab useful. If the LLM is slower or less reliable, publish
that observation. The runbook repeats on equivalent branches for each attempt;
deduplicate by family and seed when reporting its scenario-level result.

## Reproduce

```bash
.venv/bin/python -m faultline.cli run --output artifacts/held-out \
  --seeds 103 211 307 419 523 --attempts 2 --model qwen3:4b
```

The manifest records source commit/dirty status, Python/PostgreSQL environment,
model digest, protocol hash, inputs, outputs, timing, and result-file hashes.
An implementation change requires fresh affected tests; a changed model, prompt,
or evaluation protocol requires separately labelled new evaluation evidence.

The run includes model loading time if loading occurs. No automatic warm-up or
discarded slow run improves the numbers. Timeouts have measured elapsed time but
no fabricated token usage. Agent summaries are public model outputs and may use
awkward wording or contain unsupported explanations; deterministic checks determine
 recovery. Citation IDs are validated, not semantic entailment.

## Results in this repository

The public source release contains the protocol and executable checks, not a
claimed new held-out model result. CI exercises real PostgreSQL recovery without
a model. To evaluate a local model, execute the command above and retain all
attempts, including failures and abstentions. The optional model run is separate
from the automated core verification.

# Method

## Ratio

For every finished task: `ratio = estimate / actual` (the gut estimate if it was logged, else the stated estimate). Above 1 means over-estimate.
Per kind the script takes the median ratio as the correction factor and the 20th and 80th percentile as the range. A calibrated estimate is
`gut / median`, with range `gut / p80` to `gut / p20`, never narrower than ×0.6 to ×2 around the middle (small samples look more certain than they are).

Median, not mean: one 30-minute crash or one 10-second edit would otherwise dominate.

## Model runs

time ≈ first call + (calls − 1) × median seconds per call ÷ parallel calls + sequential calls × median seconds
cost ≈ calls × median cost per call + distinct long system prompts × cost of the first (cache-writing) call

Measure the per-call medians from your own call logs. In the original project: about 11.5 s and 0.04–0.05 USD for a call with a ~100k-token
cached system prompt, 8 s and 0.001 USD for a short call to a small model, 85 s and 0.5 USD for a long generation without cache.

## What to log for better calibration

- the estimate **before** starting, with a timestamp;
- the kind of work, and whether the codebase was familiar;
- time waiting for the user, separately;
- whether parallel subagents were used (an estimate that assumed sequential work will look wrong);
- crashes or scope changes, in the note, so outliers can be explained rather than averaged away.

## Known limits

The seed is 17 tasks from one project on one day, on one machine (8 GB Apple M2). Treat its factors as a starting point. With 30–50 own entries across different kinds of
work, the factors become meaningful for your setup.

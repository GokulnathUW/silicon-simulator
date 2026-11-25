# Eval cleanup

Flatten `eval/` into files. No package folders inside it.

The shared sampling rules stay as they are: 20 personas, 30 items, at most 2 sub-items of one question, seed 30, and only items every selected persona answered.

## Shared run

1. Add `eval/run.py`. Move question loading, label loading, and sampling there from `eval/wave4_holdout/`.
2. Add one function that returns the 20 full persona summaries.
3. Add one function that returns the 30 questions for those same 20 personas. It uses the same seed and limits, so a separate call still matches the personas.
4. Add one function that takes the personas, the questions, and a table name. It reads the model and both database paths from the existing settings. It loads the wave 4 labels for the given persona ids itself.
5. That function prepends `eval_` to the table name and writes one table of that name in the simulation database. Callers pass the bare name, such as `demographic`.
6. The table columns are `persona_id`, `item_id`, `predicted`, `probabilities`, `actual_label`, and `correct`. Write it only after every prediction succeeds. On a model error, write nothing and raise. If there is nothing to score, write the empty table and do not call the model.
7. Stop creating `eval_runs` and `eval_wave4_predictions`.

## Ablation

8. Add `eval/ablation.py` with one format function for each current style: demographics, Big Five, demographics plus Big Five, and the full summary left unchanged.
9. Map each style string to its format function. That map is the list of expected styles. A string that is not in the map raises.
10. Add one function that takes the style strings. It collects the 20 personas and the 30 questions once. For each string, it formats those personas with the mapped function and calls the shared run function with that string as the table name.

A later style is a new format function, a new entry in that map, and that string passed to this function.

## Repeatability

11. Add `eval/repeatability.py` with one function that takes `repeats`. It collects the 20 full summaries and the 30 questions once, then calls the shared run function that many times. The table names are `repeatability_1` through `repeatability_{repeats}`.

## Call sites

12. Point `tests/test_eval.py` and `tests/test_persona_ablation.py` at `eval/run.py`, `eval/ablation.py`, and `eval/repeatability.py`, and at the per-run tables.
13. Point `notebooks/eval_analysis.ipynb` at those modules. Read accuracy from the `eval_{name}` tables. Remove the queries that read `eval_runs`.
14. Delete `eval/wave4_holdout/`, `eval/persona_ablation/`, and `sql/eval_tables.sql`.
15. Run `pytest -q` and `ruff check . && ruff format .`.

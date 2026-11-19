# Running the corpus generation on Slurm

`scripts/generate_texts.sbatch` writes the corpus texts (layer 4) with a local model. Each job starts llama-server with Qwen3.8-27B Q8 on 2 GPUs, writes and checks every sheet of the given plants, and stops the server at the end. Run every command below from the repository folder (`~/ondemand/Context-Compaction`).

## Submit

```bash
sbatch --partition=gpu --export=ALL,VENV=$HOME/ondemand/Uncertify/.venv \
       scripts/generate_texts.sbatch mint
```

- **`--partition=gpu`:** the cluster's default partition is `cpu`, and the partition line in the script is commented out, so this flag is needed.
- **`--export=ALL,VENV=...`:** sessions here set `SLURM_EXPORT_ENV=NONE`. Without this flag the job gets neither your environment nor the venv, and `python` won't find the packages.
- **Plants:** name them before `--`. One plant (`mint`), several in order (`mint sage`), or none for all eight plants followed by the five trial ledgers. For the ledgers only: `scripts/generate_texts.sbatch -- --trials` (or `-- --trials S D`).
- **Writer options:** anything after `--` goes to `corpus.write`, e.g. `--attempts 5`, or `--sheets folk:mint:01` for single sheets. `python -m corpus.write --help` lists all of them.
- **Model settings** (the defaults of `corpus.write`): reasoning effort low for both calls; the reader decodes greedily (temperature 0), so a text's verdict does not depend on chance; token limits of 32,768 for the writer and 24,576 for the reader, thinking included, which fit the server's 65,536-token context. Override them after `--`, e.g. `-- --reasoning-effort medium`.
- **Time:** the script asks for 8 hours, which is enough for one plant (about 2–3 hours, 44 sheets). For several plants in one job, add e.g. `--time=1-00:00:00`; the `gpu` partition allows up to 2 days.

## Watch

```bash
squeue -u $USER                            # state, node and time left of your jobs
tail -f temp/potion-texts-<jobid>.out      # progress: one line per attempt, a summary per plant
tail -f temp/llama-<jobid>.log             # the model server, if something looks wrong
```

| Output | Where |
|---|---|
| What a source must imply: its claims, what it teaches, its false claims and their issues (written before the text) | `content/texts/<id>/metadata.json` |
| Accepted text | `content/texts/<id>/<id>.txt` |
| Last failed attempt, and its problems | `content/texts/<id>/failed.txt`, `failed.json` |
| Every model call (prompts, answers, timings) | `temp/corpus_write/<plant>.jsonl` |
| Images already used, per effect | `content/texts/registry.json` |

## Stop

```bash
scancel <jobid>
rm -f temp/corpus_write.lock               # cancelling leaves the lock behind; remove it before the next run
```

## Rules

- **One generation job at a time.** All runs share `content/texts/registry.json`. A second job exits at once while `temp/corpus_write.lock` exists.
- **Repeating is safe.** A job skips every text that already passes the checks. After a crash or a cancel, remove the lock and submit the same command again. `--force` rewrites texts that already pass.
- **Not inside an interactive session.** A code-server or OnDemand session is itself a Slurm job with a time limit, and Slurm kills every process in it, detached ones included, when the session ends. Submit the generation with `sbatch` so it runs as its own job.

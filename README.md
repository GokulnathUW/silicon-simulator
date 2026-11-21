# Simulator

A platform for asking how a population might respond to a campaign, offer, product change, or other decision before testing it with real people. Each persona sees a scenario, simulates human opinion.

## Versions

- **V0.** One model call per persona. No tools, no memory, no interaction between personas.
- **V1.** The same independent setup, using a reasoning model.
- **V2.** Each persona can call tools, such as checking a budget, and pull the survey answers relevant to the question. Still one-off, with no memory across runs.
- **V3.** Personas can discuss a scenario with a defined set of peers, and their reactions can change.

## Applications

Crowd runs for A/B tests, ad campaigns, and UX choices. Later, multi-turn runs with memory for cases like negotiation. Also studies that are hard to run on real people at scale, such as a bank run or an early product prototype, and trying new material against preferences a client already has, such as a streaming catalog.

## Data

The prototype uses [Twin-2K-500](https://huggingface.co/datasets/LLM-Digital-Twin/Twin-2K-500): 2,058 people and their survey answers. Prompts are then built from those tables — a persona summary, demographics, or selected questions — so later runs do not parse the raw files again.

To download dataset and create database:

run

 `python scripts/create_database.py {download_destination} {database_destination}` 

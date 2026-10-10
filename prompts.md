Spec-driven development goes in four steps, and you give one prompt per step: specify → plan → tasks → implement. Each step produces a file that the next step reads, and the constitution is checked at every step.

The main rule is to work on one small feature at a time, not the whole service.

Step 1: Specify (what and why, no technology)

Read .specify/memory/constitution.md. Write a specification for this feature:
<describe the feature in plain words: what goes in, what comes out, what counts as correct>.
Describe behaviour and acceptance criteria only, no code and no library choices.
List anything unclear as open questions. Save it to specs/001-<feature-name>/spec.md.
Do not write any code.
Read the spec, answer its open questions, and ask for corrections until it is right. A mistake here is the cheapest to fix.

Step 2: Plan (how)

Read the constitution and specs/001-<feature-name>/spec.md. Write the technical plan:
modules, data structures, function signatures, config keys, and the test approach.
Include a constitution check showing how the plan meets Principles I to VII.
Save it to specs/001-<feature-name>/plan.md. Do not write any code.
Step 3: Tasks

Read the plan in specs/001-<feature-name>/. Break it into small numbered tasks in order,
each with the files it touches and the test that proves it is done.
Save it to specs/001-<feature-name>/tasks.md. Do not write any code.
Step 4: Implement (a few tasks at a time)

Implement tasks 1 to 3 from specs/001-<feature-name>/tasks.md, following the plan
and the constitution. Write the code and its tests, then tell me the commands to run them.
Run the commands yourself, paste the output back, and then ask for the next tasks.

Suggested feature order
Each of these is one pass through the four steps:

Config and data types (evidence chunk, agent step, result record)
Evidence chunking and sentence splitting with offsets
Detector wrapper and sliding-window aggregation
Groundedness evaluator (spans, score, verdict, escalation stub)
Deterministic checks
Rule-based explanations
Result store and golden-set harness
Tips
Give the content once: for feature 1, paste the relevant sections of your brief into the specify prompt. After that the spec files carry the context.
Keep "do not write any code" in steps 1 to 3, or the assistant may jump ahead.
Start a new chat per feature if the conversation gets long. The files hold everything needed.
Spec Kit is optional: if you install it, the same steps become the commands /speckit.specify, /speckit.plan, /speckit.tasks and /speckit.implement. The plain prompts above work without it.
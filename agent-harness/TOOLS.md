# Tool Registry

These are the tools the harness can call.

## inspect_data

Reads a local file or directory and reports file names, supported data files,
and basic loading counts.

Use when:

- data is newly provided
- you need to know whether the input is parseable
- you need a first look before choosing analysis depth

## run_line_review

Runs a long-horizon line intelligence review. Best for 6-12 months of one-line
history, Short Stops, Unassigned, unclear Pareto, or production/CI management
questions.

Builds:

- visibility score
- Short Stop / Unassigned signal
- top codes
- monthly trend table
- Production Supervisor brief
- Production Manager brief
- CI Manager brief

## run_shift_workflow

Runs the tool-using shift intelligence workflow. Best for acute operating
questions involving passdown, current constraint, escalation, RCA starter,
watchlist, or 7/30/90 verification.

Builds:

- constraint
- risk score
- approval gate
- supervisor action plan
- passdown draft
- recurrence watchlist
- verification follow-ups

## write_artifact

Writes a markdown artifact into the harness workspace.

Use when:

- an answer should persist
- the agent has enough evidence to build a brief, passdown, RCA starter, or
  project note

## build_management_brief

Builds a role-based markdown brief from tool output.

Use when:

- a line review has finished
- the output needs to be readable by supervisor, production manager, and CI
  manager roles
- the agent needs a durable operating artifact instead of only JSON

## build_operating_model

Builds the floor-valid operating model from the line review.

Use when:

- recorded codes need to be separated from true physical causes
- Short Stop, Unassigned, or delayed fault assignment may distort the Pareto
- leadership needs cause classes, attribution risks, duration bias, evidence
  gaps, and owner actions before approving RCA

## build_event_fidelity_sprint

Builds a 14-day event-fidelity sprint when Short Stops, Unassigned, Unknown, or
Other are high enough to distort the Pareto.

Use when:

- the line has a visibility score below the control threshold
- Short Stops or Unassigned are among the top downtime codes
- the right next move is improving diagnostic signal before launching RCA

## update_memory

Appends a short markdown note to harness memory.

Use when:

- the agent learns something durable about a line, plant, dataset, or recurring
  issue
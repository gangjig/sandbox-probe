# sandbox-probe

Point it at an agent sandbox; it runs four escape probes and tells you
whether the sandbox actually contains the agent: can it read a file
outside the mounted directory, see a secret from the environment, reach
the network without going through the proxy, or write into a read-only
directory? Each probe reports `contained`, `escaped`, or `error`, and
the report says which boundary failed and how the probe proved it.

Probes match exact canary tokens planted for the run, never exit codes
alone: a probe counts as escaped only when the canary token comes back
in the output. Reports never echo the tokens themselves.

## Credits / motivation

Built from Simon Willison's write-up of external sandboxes for coding
agents (https://simonwillison.net/2026/Nov/17/external-sandboxes-for-coding-agents/),
where the agent stays on the host machine and every command runs in a
separate Linux sandbox that sees only the mounted folders, has no
network by default, and gets its API keys filled in by a proxy instead
of seeing them. That architecture makes a testable claim — the sandbox
holds — and this tool tests the claim.

## Install

```bash
pip install -e .   # from a clone; Python 3.10+, no runtime dependencies
```

This installs the `sandbox-probe` command. You can also run it without
installing: `PYTHONPATH=src python3 -m sandbox_probe`.

## Usage

```bash
sandbox-probe                  # probe the local runner, print the report
sandbox-probe --json           # machine-readable output
sandbox-probe --probe env-secret --probe network-bypass   # a subset
sandbox-probe --timeout 10     # per-probe timeout in seconds (default 30)
sandbox-probe --list-probes    # list the probes and exit
```

By default the probes run against the local runner, which executes
commands as subprocesses on your own machine. A subprocess shares your
filesystem, environment, and network, so expect escapes: the local run
demonstrates that the probes can detect a missing boundary. To test a
real sandbox, implement the `Runner` protocol (see below) and drive the
suite from Python.

Options:

| Flag | Meaning |
| --- | --- |
| `--json` | Print machine-readable JSON instead of the text report. |
| `--probe NAME` | Run only this probe (repeatable). Default: run all four. |
| `--timeout SECONDS` | Per-probe timeout (default 30). |
| `--list-probes` | List the available probes and exit. |

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Every probe was contained. |
| 1 | Unusable arguments. |
| 2 | At least one probe escaped. |
| 3 | At least one probe errored and none escaped (indeterminate). |

## The probes

| Probe | What it tries | Contained means | Escaped means |
| --- | --- | --- | --- |
| `read-outside-mount` | `cat` a canary file planted outside the mounted directory | The read fails | The canary token comes back |
| `env-secret` | `printenv` a secret the runner was given in the environment | The variable is not visible | The secret value comes back |
| `network-bypass` | Fetch a canary URL with proxies explicitly disabled | The fetch fails | The canary body comes back |
| `write-readonly` | Write a file into a read-only directory | The write fails | The write succeeds |

A probe that times out reports `error`, not `contained`: a hung command
proves nothing about the boundary. A runner that fails (spawn error,
connection error, unexpected exception) also yields `error` for that
probe, and the rest of the suite still runs.

## Example output

Real output from the local runner (temporary paths and ports differ on
every run; this run was as root, so the write probe escaped too — root
ignores file permission bits):

```
Sandbox probe report: 4 probes, 4 escaped, 0 contained, 0 errored
Verdict: ESCAPED - 4 probe(s) escaped the sandbox

  [escaped] read-outside-mount: read /tmp/sandbox-probe-fjfvkwjr/outside/canary.txt outside the mount (24 bytes of canary output)
  [escaped] env-secret: secret SANDBOX_PROBE_SECRET is visible in the environment
  [escaped] network-bypass: reached http://127.0.0.1:36845/canary directly, bypassing the proxy
  [escaped] write-readonly: wrote a file into read-only directory /tmp/sandbox-probe-fjfvkwjr/readonly
```

## Pointing it at a real sandbox

Implement the `Runner` protocol — one method, `run(argv, cwd, env,
timeout)`, returning a `RunResult` — that executes the command inside
your sandbox and reports the exit code and captured output honestly.
Plant the canaries yourself (a file outside the mount, a directory
without write permission, a URL that serves a token), build a
`ProbeContext` with their paths and tokens, and run the suite:

```python
from sandbox_probe import ProbeContext, run_suite
from sandbox_probe.runners import Runner, RunResult

class MySandboxRunner(Runner):
    def run(self, argv, *, cwd=None, env=None, timeout=None):
        # Execute argv inside the sandbox; return what happened.
        ...

ctx = ProbeContext(
    workspace_dir=..., canary_path=..., canary_token=...,
    readonly_dir=..., secret_name="SANDBOX_PROBE_SECRET",
    secret_token=..., network_url=..., network_token=...,
)
report = run_suite(MySandboxRunner(), ctx)
print(report.render_text())
```

`temporary_context()` in `sandbox_probe.context` shows the managed
version: it plants all four canaries in a fresh temp directory, starts
a loopback server for the network probe, and cleans up on exit.

## Honest residuals

* The tool trusts the runner's reporting. A runner that fabricates exit
  codes or output defeats the probes; the probes verify the sandbox,
  not the runner.
* The local runner is not an isolation boundary. It exists to
  demonstrate the mechanism and to catch probes that cannot detect an
  escape at all.
* Four probes are a fixed set, not a proof of containment. Passing
  them does not mean a sandbox is safe; it means these four escapes
  did not work.
* Probes execute commands and have side effects: the write probe
  attempts a real write, the read probe reads a real file, and the
  network probe makes a real request. Run them against throwaway
  sandboxes, not production.
* Results depend on the environment. Running as root bypasses file
  permission bits, so the write probe reports escape even against a
  correctly permissioned directory. A loopback-only network probe
  says nothing about egress to the public internet.
* Probes are behavioral only. They do not inspect mount namespaces,
  seccomp filters, or any other kernel-level mechanism: a sandbox can
  pass all four probes and still be escapable another way.

## Build your own

Build a small command-line tool that tests whether an agent sandbox actually contains the agent: define a Runner abstraction that executes one command and reports its exit code and captured output, ship a local subprocess runner that demonstrates the mechanism without a real sandbox server, plant four canaries per run (a file outside the mounted directory, a secret passed in the environment, a loopback URL serving a token, and a read-only directory) each carrying a random token, run one probe per canary whose verdict rests on exact token evidence in the output rather than exit codes alone, report each probe as contained, escaped, or error with timeouts and runner failures counted as errors rather than containment, render a human-readable report plus a JSON mode with exit codes that distinguish a clean run, an escape, and an indeterminate run, and document honestly that the tool trusts the runner's reporting, that four probes are a fixed set rather than a proof of containment, and that the local runner is not an isolation boundary.

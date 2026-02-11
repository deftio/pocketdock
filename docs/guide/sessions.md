# Sessions

Sessions provide persistent shell connections to a container. Unlike `run()`, which creates a new exec instance for each command, a session maintains a single long-lived shell process with preserved state (working directory, environment variables, shell history).

## Create a Session

```python
sess = c.session()
```

The session opens a `/bin/sh` shell inside the container and keeps it alive until explicitly closed or the container shuts down.

## Send and Wait

Send a command and wait for it to complete:

```python
result = sess.send_and_wait("echo hello")
result.stdout      # "hello\n"
result.exit_code   # 0
result.ok          # True
result.duration_ms # 12.3
```

With a timeout:

```python
result = sess.send_and_wait("sleep 60", timeout=5)
result.timed_out  # True
```

## Fire-and-Forget

Send a command without waiting for output:

```python
sess.send("cd /tmp")
sess.send("export MY_VAR=hello")
```

State persists across commands:

```python
sess.send("cd /tmp")
result = sess.send_and_wait("pwd")
print(result.stdout)  # "/tmp\n"
```

## Read Accumulated Output

Drain any output that has accumulated since the last read:

```python
sess.send("echo line1")
sess.send("echo line2")
import time; time.sleep(0.1)

output = sess.read()
print(output)  # "line1\nline2\n"
```

`read()` is thread-safe and clears the buffer.

## Output Callback

Register a callback for session output:

```python
sess.on_output(lambda data: print(f"[session] {data}", end=""))
```

The callback receives all output from the shell, including command echoes.

## Close

Close the session without stopping the container:

```python
sess.close()
```

After closing, any further operations raise `SessionClosed`:

```python
from pocketdock import SessionClosed

sess.close()
try:
    sess.send("echo hello")
except SessionClosed:
    print("Session is closed")
```

## Session Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | `str` | Exec instance ID backing the session |

## Sentinel Protocol

pocketdock uses a sentinel protocol to reliably detect command boundaries and exit codes. After each `send_and_wait()` command, the session injects a sentinel marker (`__PD_{uuid}_${exit_code}__`) to determine where one command's output ends and the next begins. This is transparent to the user.

## Automatic Cleanup

Sessions are automatically closed when the container shuts down:

```python
with create_new_container() as c:
    sess = c.session()
    result = sess.send_and_wait("echo hello")
# Session and container are both cleaned up
```

# Running Commands

pocket-dock supports three execution modes: **blocking**, **streaming**, and **detached**.

## Blocking Mode (Default)

Run a command, wait for it to finish, get all output at once:

```python
result = c.run("echo hello")
result.exit_code    # 0
result.stdout       # "hello\n"
result.stderr       # ""
result.ok           # True (exit_code == 0 and not timed_out)
result.duration_ms  # 47.2
result.timed_out    # False
result.truncated    # False
```

### Run Python Code

Use `lang="python"` to wrap the command with `python3 -c`:

```python
result = c.run("print(2 + 2)", lang="python")
print(result.stdout)  # "4\n"
```

### Timeout

Set a per-command timeout (in seconds):

```python
result = c.run("sleep 60", timeout=5)
result.timed_out  # True
result.ok         # False
```

The default timeout is set at container creation (30 seconds).

### Output Cap

Limit the amount of output collected:

```python
result = c.run("cat /dev/urandom | head -c 1000000", max_output=1024)
result.truncated  # True
```

Default: 10 MB (`10_485_760` bytes).

## Streaming Mode

Yield output chunks as they arrive. Useful for builds, long-running scripts, and real-time monitoring:

```python
for chunk in c.run("make all 2>&1", stream=True):
    print(chunk.data, end="")
    # chunk.stream is "stdout" or "stderr"
```

Each `StreamChunk` has:

- `stream` — `"stdout"` or `"stderr"`
- `data` — the text content

### Get Final Result After Streaming

The stream object exposes a `.result` property after iteration completes:

```python
stream = c.run("echo hello && exit 1", stream=True)
for chunk in stream:
    print(chunk.data, end="")
print(stream.result.exit_code)  # 1
```

## Detached Mode

Start a background process and get a handle to monitor or kill it:

```python
proc = c.run("python -m http.server 8080", detach=True)
proc.is_running()  # True
```

### Read Buffered Output

Detached processes write to a ring buffer (1 MB default). Read from it without blocking:

```python
# Consume and clear the buffer
output = proc.read()
print(output.stdout)
print(output.stderr)

# Peek without consuming
output = proc.peek()
```

Both return a `BufferSnapshot` with `.stdout` and `.stderr` strings.

### Buffer Overflow

Check if the ring buffer has overflowed (older data was evicted):

```python
proc.buffer_size      # Current bytes in buffer
proc.buffer_overflow  # True if data was evicted
```

### Wait for Completion

```python
result = proc.wait(timeout=60)  # -> ExecResult
print(result.exit_code)
```

### Kill

```python
proc.kill()           # Send SIGTERM (default)
proc.kill(signal=9)   # Send SIGKILL
```

## Callbacks

Register callbacks to be notified of output and exit events on detached processes:

```python
c.on_stdout(lambda container, data: print(f"[out] {data}", end=""))
c.on_stderr(lambda container, data: print(f"[err] {data}", end=""))
c.on_exit(lambda container, code: print(f"Exited with code {code}"))

proc = c.run("python long_task.py", detach=True)
```

Callback signatures:

- `on_stdout(fn)` — `fn(container, data: str)`
- `on_stderr(fn)` — `fn(container, data: str)`
- `on_exit(fn)` — `fn(container, exit_code: int)`

Callbacks are invoked for all detached processes on the container. They are dispatched synchronously from the read loop.

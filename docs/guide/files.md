# File Operations

pocketdock provides five methods for moving data between the host and container.

## Write a File

Write text or binary content into the container:

```python
# Write text
c.write_file("/home/sandbox/config.json", '{"debug": true}')

# Write binary
c.write_file("/home/sandbox/data.bin", b"\x00\x01\x02\x03")
```

The file is created (or overwritten) at the specified path. Parent directories must exist.

## Read a File

Read file contents from the container (returns `bytes`):

```python
data = c.read_file("/home/sandbox/output.txt")
print(data.decode())  # decode to string if needed
```

## List Files

List a directory inside the container:

```python
files = c.list_files("/home/sandbox/")
# ["config.json", "output.txt", "src/"]
```

Default path is `/home/sandbox`.

```python
files = c.list_files()  # Lists /home/sandbox
```

## Push (Host to Container)

Copy a file or directory from the host into the container:

```python
# Push a single file
c.push("./local_script.py", "/home/sandbox/script.py")

# Push an entire directory
c.push("./src/", "/home/sandbox/src/")
```

## Pull (Container to Host)

Copy a file or directory from the container to the host:

```python
# Pull a single file
c.pull("/home/sandbox/results.csv", "./results.csv")

# Pull a directory
c.pull("/home/sandbox/output/", "./output/")
```

## How It Works

File operations use the container engine's tar archive API under the hood:

- `write_file()` creates a single-file tar archive and streams it into the container
- `read_file()` pulls a tar archive from the container and extracts the file
- `push()` and `pull()` use the same tar mechanism for files and directories
- `list_files()` executes `ls` inside the container

All operations open a fresh Unix socket connection (connection-per-operation), so file transfers don't block other operations.

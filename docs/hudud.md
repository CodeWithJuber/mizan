# Hudud (حدود): the limits of a program MIZAN runs on your project

When a request works on the selected project's files ("count the ERROR lines in `app.log` and write `errors.csv`"), Lisan writes a program and MIZAN runs it in the project's isolated sandbox; what the program changes is applied back to the project. Hudud (`backend/tadbir/hudud.py`) puts a guard in front of the program's first line, using Python's audit hooks (PEP 578), which the program cannot remove:

- inside the project, only the files the request names as outputs can be opened for writing (a file that exists is writable only when the request says to save, write or update it); reading is free
- nothing inside the project is deleted, renamed or truncated
- no other program is started (`subprocess`, `os.system`, `exec`, `spawn`, `fork`) and no native library is loaded (`ctypes`)

Writing outside the project (`/tmp`) stays allowed. After the run MIZAN still checks the files the sandbox reports as changed: a change to a file the request did not allow is a problem it repairs or reports, never a success. It also checks that each output the request names was written (a JSON output must parse, a CSV one must not be empty). Lisan repairs a failing program at most twice; when the guard stopped it, the repair request names the files it may write.

The same guard (with no writable files) wraps programs MIZAN runs over a web page to answer a question about a table ("the cheapest item rated 4 stars or more").

This keeps the request's own limits inside the sandbox: text in a file (see [Amanah](amanah.md)) or a mistaken program cannot make MIZAN change what the user did not ask for.

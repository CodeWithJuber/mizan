# data-dir-in-ci

Tests run with MIZAN_DATA_DIR unset and CI's runner is not root, so the default /data/mizan cannot be created there. Any store a chat touches must survive an uncreatable data dir (approvals.chat_context does); reproduce CI with MIZAN_DATA_DIR=/proc/mizan-nope.

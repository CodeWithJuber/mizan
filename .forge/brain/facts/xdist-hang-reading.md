# xdist-hang-reading

CI's Test job runs pytest -n auto --dist loadscope on 2 workers with --cov=backend. A worker's last printed test is often only waiting for more work; the hung test is the one whose start line has no result line.

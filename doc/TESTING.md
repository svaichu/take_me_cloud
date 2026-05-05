Create tooling with following scenarios:

1. Auth is successful.
2. List studios is successful.
3. --lock-ssh works as expected. Match the studios listed with -ls and the hosts added to .ssh/config. Pass only if all -ls studios are in .ssh/config and there are no lightning hosts in .ssh/config that are not in the -ls list. Make sure no non-lightning hosts are removed from .ssh/config.
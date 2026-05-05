Create a cli with the name "take-me-cloud"

Functionalities:
1. Connect to lightning AI using lightning_sdk. Auth using the env vars $LIGHTNING_API_KEY and $LIGHTNING_USER_ID. Read those envs from shell. 

2. List all existing studios. Check for all studios in all teamspaces and organizations the user has access to. Print the list of studios in a nice format. When the cli is run with flag --list or -ls. Show status of each studio (running, stopped, etc).

3. Lock .ssh/* files. When the cli is run with flag --lock-ssh. Make sure all the studios listed with -ls are added to the .ssh/config file. Use the lightning_sdk connect, follow their standard for ssh config. DO NOT REMOVE ANY NON-LIGHTNING HOST. If there are any existing lightning hosts that are not in the current list of studios, remove them from the .ssh/config file.
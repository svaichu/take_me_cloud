This package is meant for easily spining up a cloud instance from Lightning AI studio. And adding it .ssh/config file for easy ssh access.

Create a cli with the name "take-me-cloud"

Functionalities:
1. Connect to lightning AI using lightning_sdk. Auth using the env vars $LIGHTNING_API_KEY and $LIGHTNING_USER_ID. Read those envs from shell. 

2. List all existing studios. Check for all studios in all teamspaces and organizations the user has access to. Print the list of studios in a nice format. When the cli is run with flag --list or -ls. Show status of each studio (running, stopped, etc).
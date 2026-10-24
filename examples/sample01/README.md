# grpc_frame minimal example

Run from the `example/` directory, with `grpc_frame` installed. Start `python -m server_grpc.server` in one terminal, then `python client.py` in another. No hardware or generated project-specific protobuf files are required. `server_value.txt` is written on the server; `client_value.txt` and `also_client_value.txt` are written on the client. For the same-machine demonstration these files happen to share a filesystem, so run the client and server in separate directories or hosts when verifying placement.

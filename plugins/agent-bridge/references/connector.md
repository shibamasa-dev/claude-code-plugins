# Find the Supabase connector and project

Shared by the `setup` and `add` skills.

- Find a connector **by what it can do**, not by its name: tools that run SQL (`execute_sql(project_id, query)`), apply a migration (`apply_migration(project_id, name, query)`) and deploy an Edge Function (`deploy_edge_function(project_id, name, entrypoint_path, verify_jwt, files)`). With a saved connector, use it. Without one, list projects (`list_projects`) and ask the user which project to use.
- If no such connector is available, stop and tell the user to connect Supabase (claude.ai connector or MCP server). Don't fall back to something else.
- Save with `claude plugin configure agent-bridge@shibamasa-plugins --values-stdin` (the id from `claude plugin list` if it came from another marketplace) and JSON on stdin, for example `{"supabase_connector":"<server>","supabase_project_id":"<id>"}`. Where you can't run the `claude` CLI, ask the user to set them in the plugin's settings.

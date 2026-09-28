UPDATE agents SET policy = '{
  "allowed_tools": ["get_verse", "search_verses", "save_reflection"],
  "approval_required_tools": ["save_reflection"],
  "max_steps_per_run": 5,
  "max_cost_per_run_usd": 0.01
}' WHERE name = 'verse-finder';

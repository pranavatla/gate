local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local need     = tonumber(ARGV[3])
local cost     = tonumber(ARGV[4])
local force    = tonumber(ARGV[5])

local t   = redis.call("TIME")
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

local state  = redis.call("HMGET", key, "tokens", "ts")
local tokens = tonumber(state[1]) or capacity
local ts     = tonumber(state[2]) or now

tokens = math.min(capacity, tokens + (now - ts) / 1000 * rate)

local allowed = 0
if force == 1 or tokens >= need then
  tokens = tokens - cost
  allowed = 1
end

redis.call("HSET", key, "tokens", tokens, "ts", now)
redis.call("PEXPIRE", key, math.ceil(capacity / rate * 1000) + 1000)

local retry_ms = 0
if allowed == 0 then
  retry_ms = math.ceil((need - tokens) / rate * 1000)
end

return {allowed, math.floor(tokens), retry_ms}

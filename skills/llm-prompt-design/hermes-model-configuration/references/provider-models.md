# Provider-Model Reasoning Configuration

**Summary**: 5 providers, 525 total models, 77 with reasoning_effort configured.

## OpenRouter (396 models, 49 with reasoning)

### HIGH (3)
- anthropic/claude-opus-5-fast
- anthropic/claude-opus-5
- anthropic/claude-opus-5:batch

### MEDIUM (17)
- anthropic/claude-opus-4.8-fast
- anthropic/claude-opus-4.8, :batch
- anthropic/claude-opus-4.7-fast, 4.7, :batch, 4.6, :batch
- anthropic/claude-opus-4.5, :batch
- anthropic/claude-opus-4.1, :batch
- anthropic/claude-opus-4
- deepseek/deepseek-r1 (all variants)

### LOW (29)
- z-ai/glm-* (5.3-flash, 5.3-flash:batch, 5.3, 5.2, 5.2:free, 5.1, 5v-turbo, 5-turbo, 5, 4.7-flash, 4.7, 4.6v, 4.6, 4.5v, 4.5, 4.5-air)
- anthropic/claude-* (sonnet-5, sonnet-5:batch, sonnet-4.6, sonnet-4.6:batch, sonnet-4.5, sonnet-4.5:batch, sonnet-4, haiku-latest, haiku-4.5, haiku-4.5:batch, claude-3-haiku)

---

## Api.b.ai (44 models, 13 with reasoning)

### HIGH (1)
- claude-opus-5

### MEDIUM (4)
- claude-opus-4.8, 4.7, 4.6, 4.5

### LOW (8)
- glm-5.1, 5.2, 5.3, 5.3-flash
- claude-sonnet-5, 4.6, 4.5, haiku-4.5

---

## Api.linstore.my.id (20 models, 10 with reasoning)

### HIGH (2)
- claude-opus-4-8
- claude-opus-5

### MEDIUM (3)
- claude-opus-4-5, 4-6, 4-7

### LOW (5)
- claude-haiku-4-5
- claude-sonnet-4-5, 4-6, 5
- glm-5.3-free

**Note**: GLM-5.3-free **wajib** reasoning_effort:low. Without it, linstore returns HTTP 400: `该模型始终思考，不支持关闭思考` ("model always reasons, reasoning cannot be disabled").

---

## Api.invibuilder.com (46 models, 4 with reasoning)

### LOW (4)
- a1/glm-5.1, 5.2, 5.3
- z-ai/glm-5.2:free

---

## Api.hcnsec.cn (19 models, 1 with reasoning)

### LOW (1)
- glm-4.5-air

---

## Configuration Command Pattern

For each model, run:
```bash
hermes config set providers.<PROVIDER>.models.<MODEL-ID>.reasoning_effort <low|medium|high>
```

Example:
```bash
hermes config set providers.Api.linstore.my.id.models.glm-5.3-free.reasoning_effort low
hermes config set providers.OpenRouter.models.anthropic/claude-opus-5.reasoning_effort high
```

---

## Session Record

**Batch execution**: August 31, 2026  
**Script**: `~/set_all_reasoning.sh`  
**Log**: `~/set_all_reasoning.log`  
**Total commands**: 77 (all succeeded)  
**Batch runtime**: ~4 minutes

All `hermes config set` commands written to `~/.hermes/config.yaml` and cached in-memory at Hermes startup.
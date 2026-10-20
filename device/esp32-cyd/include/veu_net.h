#pragma once
#include "veu_config.h"
#include "veu_state.h"

bool veuWifiConnect(VeuConfig& cfg, uint32_t timeoutMs = 20000);
void veuWifiPortalBegin();           // AP veu-placa + captive form
bool veuWifiPortalLoop(VeuConfig& cfg); // true when saved+restart needed
bool veuFetchState(const VeuConfig& cfg, VeuState& st);
bool veuPostEvent(const VeuConfig& cfg, const char* type, const char* payload);

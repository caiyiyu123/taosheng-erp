<template>
  <div class="ts-finance">
    <div class="ts-finance-toolbar">
      <el-tabs v-model="activeTab" class="ts-finance-tabs">
        <el-tab-pane label="🌐 跨境店 (CNY)" name="cross_border" />
        <el-tab-pane label="🇷🇺 本土店 (RUB)" name="local" />
      </el-tabs>
      <el-button type="primary" :icon="Refresh" @click="syncDialogVisible = true">
        手动同步
      </el-button>
    </div>

    <FinanceTabContent v-if="activeTab === 'cross_border'" shop-type="cross_border" />
    <FinanceTabContent v-else shop-type="local" />

    <FinanceSyncDialog v-model="syncDialogVisible" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import FinanceTabContent from '../components/finance/FinanceTabContent.vue'
import FinanceSyncDialog from '../components/finance/FinanceSyncDialog.vue'

const activeTab = ref('cross_border')
const syncDialogVisible = ref(false)
</script>

<style scoped>
.ts-finance { padding: 16px; }
.ts-finance-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px;
}
.ts-finance-tabs { flex: 1; }
</style>

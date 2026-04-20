<template>
  <div class="ts-tab">
    <div class="ts-filters">
      <el-select v-model="filters.shop_id" placeholder="全部店铺" clearable style="width: 200px">
        <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        :clearable="false"
        value-format="YYYY-MM-DD"
        style="width: 240px"
      />
      <div class="ts-date-shortcuts">
        <el-button size="small" @click="setRange('thisWeek')">本周</el-button>
        <el-button size="small" @click="setRange('lastWeek')">上周</el-button>
        <el-button size="small" @click="setRange('thisMonth')">本月</el-button>
        <el-button size="small" @click="setRange('last4weeks')">最近4周</el-button>
      </div>
    </div>

    <FinanceSummaryCards :summary="summary" :loading="loading.summary" />

    <div v-if="summary.missing_mapping_count > 0" class="ts-missing-banner">
      ⚠ {{ summary.missing_mapping_count }} 条订单采购成本缺失
      <el-link type="primary" @click="goToMappings">去 SKU 映射</el-link>
    </div>

    <el-divider content-position="left">📋 订单明细</el-divider>
    <FinanceOrdersTable
      :shop-type="shopType"
      :shop-id="filters.shop_id"
      :date-from="dateRange[0]"
      :date-to="dateRange[1]"
      :currency="summary.currency"
      @reload="reloadAll"
    />

    <el-divider content-position="left">💰 其他费用</el-divider>
    <FinanceOtherFeesTable
      :shop-type="shopType"
      :shop-id="filters.shop_id"
      :date-from="dateRange[0]"
      :date-to="dateRange[1]"
      :currency="summary.currency"
    />

    <el-divider content-position="left">🔎 对账</el-divider>
    <FinanceReconciliation
      :shop-type="shopType"
      :shop-id="filters.shop_id"
      :date-from="dateRange[0]"
      :date-to="dateRange[1]"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../../api'
import FinanceSummaryCards from './FinanceSummaryCards.vue'
import FinanceOrdersTable from './FinanceOrdersTable.vue'
import FinanceOtherFeesTable from './FinanceOtherFeesTable.vue'
import FinanceReconciliation from './FinanceReconciliation.vue'

const props = defineProps({
  shopType: { type: String, required: true },
})

const router = useRouter()
const shops = ref([])
const filters = reactive({ shop_id: null })
const dateRange = ref(getLast4WeeksRange())
const summary = ref({ currency: 'RUB', order_count: 0, total_net_to_seller: 0, total_commission: 0,
  total_delivery_fee: 0, total_fine: 0, total_storage: 0, total_deduction: 0,
  total_purchase_cost: 0, total_net_profit: 0, total_other_fees: 0, final_profit: 0,
  missing_mapping_count: 0 })
const loading = reactive({ summary: false })

function getLast4WeeksRange() {
  const end = new Date()
  const start = new Date(end.getTime() - 27 * 86400000)
  const fmt = d => d.toISOString().slice(0, 10)
  return [fmt(start), fmt(end)]
}

function setRange(key) {
  const today = new Date()
  const day = today.getDay() || 7
  const fmt = d => d.toISOString().slice(0, 10)
  if (key === 'thisWeek') {
    const monday = new Date(today.getTime() - (day - 1) * 86400000)
    dateRange.value = [fmt(monday), fmt(today)]
  } else if (key === 'lastWeek') {
    const lastMon = new Date(today.getTime() - (day + 6) * 86400000)
    const lastSun = new Date(today.getTime() - day * 86400000)
    dateRange.value = [fmt(lastMon), fmt(lastSun)]
  } else if (key === 'thisMonth') {
    const first = new Date(today.getFullYear(), today.getMonth(), 1)
    dateRange.value = [fmt(first), fmt(today)]
  } else {
    dateRange.value = getLast4WeeksRange()
  }
}

async function fetchShops() {
  try {
    const { data } = await api.get('/api/shops')
    shops.value = (data || []).filter(s => s.type === props.shopType)
  } catch (e) { console.warn('shops error', e) }
}

async function fetchSummary() {
  loading.summary = true
  try {
    const params = {
      shop_type: props.shopType,
      date_from: dateRange.value[0], date_to: dateRange.value[1],
    }
    if (filters.shop_id) params.shop_id = filters.shop_id
    const { data } = await api.get('/api/finance/summary', { params })
    summary.value = data
  } catch (e) { console.warn('summary error', e) }
  finally { loading.summary = false }
}

function reloadAll() {
  fetchSummary()
}

function goToMappings() {
  router.push({ path: '/sku-mappings', query: filters.shop_id ? { shop_id: filters.shop_id } : {} })
}

watch(() => props.shopType, () => {
  filters.shop_id = null
  fetchShops()
  fetchSummary()
})
watch([() => filters.shop_id, dateRange], fetchSummary, { deep: true })

onMounted(() => {
  fetchShops()
  fetchSummary()
})
</script>

<style scoped>
.ts-tab { padding: 8px 0; }
.ts-filters { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.ts-date-shortcuts { display: flex; gap: 6px; }
.ts-missing-banner {
  padding: 10px 14px; margin: 12px 0;
  background: #fffbea; border: 1px solid #fcd34d; border-radius: 6px;
  color: #92400e; font-size: 13px;
}
</style>

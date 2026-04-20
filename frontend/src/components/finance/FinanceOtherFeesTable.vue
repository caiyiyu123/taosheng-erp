<template>
  <el-collapse v-model="open">
    <el-collapse-item name="fees">
      <template #title>
        <span class="ts-title">💰 其他费用 ({{ total }} 条)</span>
      </template>
      <el-table :data="items" stripe :fit="false" v-loading="loading" max-height="400">
        <el-table-column prop="sale_date" label="日期" width="110" />
        <el-table-column label="类型" width="140">
          <template #default="{ row }">
            <el-tag :type="typeColor(row.fee_type)" size="small">{{ typeLabel(row.fee_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.amount) }} {{ symbol }}</template>
        </el-table-column>
        <el-table-column prop="fee_description" label="描述" min-width="300" show-overflow-tooltip />
      </el-table>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api from '../../api'

const props = defineProps({
  shopType: String, shopId: [Number, null], dateFrom: String, dateTo: String, currency: String,
})
const open = ref([])
const items = ref([])
const total = ref(0)
const loading = ref(false)
const symbol = computed(() => props.currency === 'CNY' ? '¥' : '₽')

const TYPE_LABEL = { storage: '仓储', fine: '罚款', deduction: '扣款', logistics_adjust: '物流调整', other: '其他' }
const TYPE_COLOR = { storage: 'info', fine: 'danger', deduction: 'warning', logistics_adjust: '', other: '' }
function typeLabel(t) { return TYPE_LABEL[t] || t }
function typeColor(t) { return TYPE_COLOR[t] || '' }
function fmt(v) { return Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

async function refresh() {
  loading.value = true
  try {
    const params = { shop_type: props.shopType, date_from: props.dateFrom, date_to: props.dateTo }
    if (props.shopId) params.shop_id = props.shopId
    const { data } = await api.get('/api/finance/other-fees', { params })
    items.value = data.items
    total.value = data.total
    if (total.value > 0 && !open.value.includes('fees')) open.value.push('fees')
  } catch (e) { console.warn('other-fees error', e) }
  finally { loading.value = false }
}

watch(() => [props.shopType, props.shopId, props.dateFrom, props.dateTo], refresh)
onMounted(refresh)
</script>

<style scoped>
.ts-title { font-weight: 600; color: #1e293b; }
</style>

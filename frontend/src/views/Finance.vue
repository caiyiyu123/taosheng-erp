<template>
  <div>
    <el-card style="margin-bottom: 20px">
      <div style="display: flex; gap: 12px; margin-bottom: 16px">
        <el-select v-model="filters.shop_id" placeholder="全部店铺" clearable @change="fetchFinance">
          <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <el-select v-model="filters.order_type" placeholder="订单类型" clearable @change="fetchFinance">
          <el-option label="FBS" value="FBS" />
          <el-option label="FBW" value="FBW" />
        </el-select>
      </div>
      <el-row :gutter="16">
        <el-col :span="5">
          <el-statistic title="销售额" :value="summary.total_sales" prefix="¥" />
        </el-col>
        <el-col :span="5">
          <el-statistic title="采购成本" :value="summary.total_purchase_cost" prefix="¥" />
        </el-col>
        <el-col :span="4">
          <el-statistic title="佣金" :value="summary.total_commission" prefix="¥" />
        </el-col>
        <el-col :span="4">
          <el-statistic title="物流费" :value="summary.total_logistics" prefix="¥" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="利润" :value="summary.total_profit" prefix="¥" :value-style="{ color: summary.total_profit >= 0 ? '#22c55e' : '#ef4444' }" />
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const shops = ref([])
const filters = reactive({ shop_id: '', order_type: '' })
const summary = ref({ total_sales: 0, total_commission: 0, total_logistics: 0, total_purchase_cost: 0, total_profit: 0 })

async function fetchFinance() {
  try {
    const params = {}
    if (filters.shop_id) params.shop_id = filters.shop_id
    if (filters.order_type) params.order_type = filters.order_type
    const { data } = await api.get('/api/finance/summary', { params })
    summary.value = data
  } catch (e) {
    console.error('Fetch finance error:', e)
    ElMessage.error('数据加载失败')
  }
}

onMounted(async () => {
  try {
    shops.value = (await api.get('/api/shops')).data
  } catch (e) {
    console.error('Fetch shops error:', e)
  }
  fetchFinance()
})
</script>

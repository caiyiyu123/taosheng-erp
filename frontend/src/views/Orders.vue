<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px">
        <span>订单列表</span>
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
          <el-input v-model="filters.search" placeholder="搜索订单号 / 产品SKU" clearable style="width: 220px" @keyup.enter="onSearch" @clear="onSearch">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="filters.order_type" placeholder="订单类型" clearable style="width: 120px" @change="onSearch">
            <el-option label="FBS" value="FBS" />
            <el-option label="FBW" value="FBW" />
          </el-select>
          <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px" @change="onSearch">
            <el-option label="待发货" value="pending" />
            <el-option label="配送中" value="in_transit" />
            <el-option label="已完成" value="completed" />
            <el-option label="已取消" value="cancelled" />
            <el-option label="已拒收" value="rejected" />
            <el-option label="已退货" value="returned" />
          </el-select>
        </div>
      </div>
    </template>
    <el-table :data="orders" stripe>
      <el-table-column label="图片" width="70">
        <template #default="{ row }">
          <el-image
            v-if="row.items && row.items.length && row.items[0].image_url"
            :src="row.items[0].image_url"
            style="width: 44px; height: 44px; border-radius: 4px"
            fit="cover"
          >
            <template #error><span style="color: #ccc; font-size: 12px">无图</span></template>
          </el-image>
          <span v-else style="color: #ccc; font-size: 12px">无图</span>
        </template>
      </el-table-column>
      <el-table-column prop="wb_order_id" label="订单号" min-width="130" />
      <el-table-column label="产品SKU" min-width="130">
        <template #default="{ row }">
          <span v-if="row.items && row.items.length">{{ row.items[0].sku }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="order_type" label="类型" min-width="70">
        <template #default="{ row }">
          <el-tag :type="row.order_type === 'FBS' ? 'success' : 'primary'" size="small">{{ row.order_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="total_price" label="金额" min-width="100">
        <template #default="{ row }">{{ currencySymbol(row.currency) }} {{ row.total_price?.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" min-width="80">
        <template #default="{ row }">
          <span :style="{ color: statusColor(row.status), fontWeight: 'bold' }">{{ statusLabel(row.status) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="下单时间" min-width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="$router.push(`/orders/${row.id}`)">订单详情</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :total="total" :page-size="50" layout="total, prev, pager, next" style="margin-top: 16px" @current-change="fetchOrders" />
  </el-card>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import api from '../api'

const route = useRoute()
const orders = ref([])
const total = ref(0)
const page = ref(1)
const filters = reactive({ search: '', order_type: route.query.order_type || '', status: '' })

function onSearch() {
  page.value = 1
  fetchOrders()
}

const STATUS_MAP = {
  pending: '待发货', in_transit: '配送中',
  completed: '已完成', cancelled: '已取消', rejected: '已拒收', returned: '已退货',
}
const STATUS_COLOR = {
  pending: '#606266', in_transit: '#409eff', completed: '#67c23a',
  cancelled: '#e6a23c', rejected: '#f56c6c', returned: '#909399',
}

function statusLabel(status) {
  return STATUS_MAP[status] || status
}
function statusColor(status) {
  return STATUS_COLOR[status] || '#606266'
}

function currencySymbol(currency) {
  const map = { RUB: '₽', CNY: '¥', USD: '$', EUR: '€', BYN: 'Br', KZT: '₸' }
  return map[currency] || currency
}

function formatTime(dt) {
  if (!dt) return ''
  // Backend stores UTC but returns without 'Z' suffix — ensure JS treats it as UTC
  const utcDt = String(dt).endsWith('Z') ? dt : dt + 'Z'
  return new Date(utcDt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}

async function fetchOrders() {
  const params = { page: page.value }
  if (filters.search) params.search = filters.search
  if (filters.order_type) params.order_type = filters.order_type
  if (filters.status) params.status = filters.status
  const { data } = await api.get('/api/orders', { params })
  orders.value = data.items
  total.value = data.total
}

onMounted(fetchOrders)
</script>

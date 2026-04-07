<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px">
        <div style="display: flex; align-items: center; gap: 12px">
          <span>订单列表</span>
          <el-button type="primary" size="small" :loading="syncing" @click="syncOrders">
            {{ syncing ? '同步中...' : '同步订单' }}
          </el-button>
          <el-popconfirm title="将清空所有订单数据并重新抓取，确定继续？" @confirm="fullSyncOrders">
            <template #reference>
              <el-button type="warning" size="small" :loading="syncing">
                {{ syncing ? '同步中...' : '全量同步' }}
              </el-button>
            </template>
          </el-popconfirm>
        </div>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap">
          <el-button v-for="p in datePresets" :key="p.label"
            :type="activeDatePreset === p.label ? 'primary' : 'default'" size="small"
            @click="applyDatePreset(p)">{{ p.label }}</el-button>
          <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
            start-placeholder="开始日期" end-placeholder="结束日期" size="small"
            value-format="YYYY-MM-DD" style="width: 240px" @change="onDateRangeChange" />
          <el-input v-model="filters.search" placeholder="搜索订单号 / 产品SKU" clearable style="width: 200px" size="small" @keyup.enter="onSearch" @clear="onSearch">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="filters.shop_id" placeholder="全部店铺" clearable style="width: 140px" size="small" @change="onSearch">
            <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
          <el-select v-model="filters.order_type" placeholder="全部订单" clearable style="width: 110px" size="small" @change="onSearch">
            <el-option label="全部订单" value="" />
            <el-option label="FBS" value="FBS" />
            <el-option label="FBW" value="FBW" />
          </el-select>
          <el-select v-model="filters.status" placeholder="状态" clearable style="width: 110px" size="small" @change="onSearch">
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
      <el-table-column prop="price_rub" label="金额(₽)" min-width="100">
        <template #default="{ row }">₽{{ Math.round(row.price_rub || 0)?.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column prop="price_cny" label="金额(¥)" min-width="100">
        <template #default="{ row }">¥{{ (row.price_cny || 0)?.toLocaleString() }}</template>
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
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const route = useRoute()
const orders = ref([])
const total = ref(0)
const page = ref(1)
const shops = ref([])
const syncing = ref(false)
const filters = reactive({ search: '', shop_id: '', order_type: route.query.order_type || '', status: '', date_from: '', date_to: '' })
const dateRange = ref(null)
const activeDatePreset = ref('')

const today = new Date()
function fmt(d) { return d.toISOString().slice(0, 10) }
function addDays(d, n) { const r = new Date(d); r.setDate(r.getDate() + n); return r }

const datePresets = [
  { label: '全部', from: '', to: '' },
  { label: '今日', from: fmt(today), to: fmt(today) },
  { label: '昨日', from: fmt(addDays(today, -1)), to: fmt(addDays(today, -1)) },
  { label: '近7天', from: fmt(addDays(today, -6)), to: fmt(today) },
  { label: '近30天', from: fmt(addDays(today, -29)), to: fmt(today) },
]

function applyDatePreset(p) {
  activeDatePreset.value = p.label
  filters.date_from = p.from
  filters.date_to = p.to
  dateRange.value = p.from && p.to ? [p.from, p.to] : null
  onSearch()
}

function onDateRangeChange(val) {
  if (val && val.length === 2) {
    activeDatePreset.value = ''
    filters.date_from = val[0]
    filters.date_to = val[1]
  } else {
    filters.date_from = ''
    filters.date_to = ''
  }
  onSearch()
}

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
  return new Date(utcDt).toLocaleString('zh-CN', { timeZone: 'Europe/Moscow' })
}

let syncPollTimer = null

async function syncOrders() {
  syncing.value = true
  try {
    await api.post('/api/orders/sync')
    // Poll status until done
    let pollCount = 0
    syncPollTimer = setInterval(async () => {
      pollCount++
      if (pollCount > 60) {
        clearInterval(syncPollTimer)
        syncPollTimer = null
        syncing.value = false
        ElMessage.warning('同步超时，请稍后重试')
        return
      }
      try {
        const { data } = await api.get('/api/orders/sync/status')
        if (data.status === 'done') {
          clearInterval(syncPollTimer)
          syncPollTimer = null
          syncing.value = false
          ElMessage.success(data.detail || '订单同步完成')
          fetchOrders()
        } else if (data.status === 'error') {
          clearInterval(syncPollTimer)
          syncPollTimer = null
          syncing.value = false
          ElMessage.error('同步失败: ' + (data.detail || '未知错误'))
        }
      } catch { /* keep polling */ }
    }, 2000)
  } catch {
    syncing.value = false
    ElMessage.error('同步请求失败')
  }
}

async function fullSyncOrders() {
  syncing.value = true
  try {
    await api.post('/api/orders/full-sync')
    let pollCount = 0
    syncPollTimer = setInterval(async () => {
      pollCount++
      if (pollCount > 120) {
        clearInterval(syncPollTimer)
        syncPollTimer = null
        syncing.value = false
        ElMessage.warning('全量同步超时，请稍后查看')
        return
      }
      try {
        const { data } = await api.get('/api/orders/sync/status')
        if (data.status === 'done') {
          clearInterval(syncPollTimer)
          syncPollTimer = null
          syncing.value = false
          ElMessage.success(data.detail || '全量同步完成')
          fetchOrders()
        } else if (data.status === 'error') {
          clearInterval(syncPollTimer)
          syncPollTimer = null
          syncing.value = false
          ElMessage.error('同步失败: ' + (data.detail || '未知错误'))
        }
      } catch { /* keep polling */ }
    }, 2000)
  } catch {
    syncing.value = false
    ElMessage.error('全量同步请求失败')
  }
}

async function fetchOrders() {
  try {
    const params = { page: page.value }
    if (filters.search) params.search = filters.search
    if (filters.shop_id) params.shop_id = filters.shop_id
    if (filters.order_type) params.order_type = filters.order_type
    if (filters.status) params.status = filters.status
    if (filters.date_from) params.date_from = filters.date_from
    if (filters.date_to) params.date_to = filters.date_to
    const { data } = await api.get('/api/orders', { params })
    orders.value = data.items
    total.value = data.total
  } catch (e) {
    console.error('Fetch orders error:', e)
    ElMessage.error('数据加载失败')
  }
}

onMounted(async () => {
  try {
    const { data } = await api.get('/api/shops')
    shops.value = data
  } catch (e) { /* ignore */ }
  fetchOrders()
})

onUnmounted(() => {
  if (syncPollTimer) {
    clearInterval(syncPollTimer)
    syncPollTimer = null
  }
})
</script>

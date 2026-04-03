<template>
  <div>
    <!-- 日期筛选 -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px;">
      <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
        <el-select v-model="shopId" placeholder="全部店铺" clearable size="small" style="width: 150px" @change="fetchAll">
          <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <el-button v-for="preset in presets" :key="preset.label"
          :type="activePreset === preset.label ? 'primary' : 'default'" size="small"
          @click="applyPreset(preset)">{{ preset.label }}</el-button>
        <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
          start-placeholder="开始日期" end-placeholder="结束日期" size="small"
          value-format="YYYY-MM-DD" @change="onDateChange" />
      </div>
    </div>

    <!-- KPI 卡片 -->
    <el-row :gutter="12" style="margin-bottom: 20px">
      <el-col :span="3" v-for="kpi in kpis" :key="kpi.label">
        <el-card shadow="hover" :body-style="{ padding: '14px' }">
          <div class="ts-stat-label" style="white-space: nowrap">{{ kpi.label }}</div>
          <div :style="{ fontSize: '20px', fontWeight: 'bold', marginTop: '6px', color: kpi.color || 'var(--ts-text-heading)', whiteSpace: 'nowrap' }">
            {{ fmtKpi(kpi.value, kpi.prefix) }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图 -->
    <el-card style="margin-bottom: 20px">
      <template #header>推广趋势</template>
      <v-chart :option="chartOption" style="height: 280px" autoresize />
    </el-card>

    <!-- 广告活动列表 -->
    <el-card style="margin-bottom: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>广告活动</span>
          <div style="display: flex; gap: 8px">
            <el-button v-for="s in campaignStatusFilters" :key="s.value"
              :type="campaignStatus === s.value ? 'primary' : 'default'" size="small"
              @click="campaignStatus = s.value; fetchAll()">{{ s.label }}</el-button>
          </div>
        </div>
      </template>
      <el-table :data="campaigns" stripe>
        <el-table-column prop="name" label="活动名称" min-width="180" />
        <el-table-column prop="wb_advert_id" label="活动ID" min-width="120" />
        <el-table-column prop="type" label="类型" min-width="80">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.type)" size="small">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" min-width="80">
          <template #default="{ row }">
            <span :style="{ color: statusColor(row.status), fontWeight: 'bold' }">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="total_spend" label="花费" min-width="100">
          <template #default="{ row }">₽{{ Math.round(row.total_spend)?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="total_views" label="展示" min-width="90">
          <template #default="{ row }">{{ row.total_views?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="total_clicks" label="点击" min-width="80">
          <template #default="{ row }">{{ row.total_clicks?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="total_orders" label="订单" min-width="70" />
        <el-table-column prop="roas" label="ROAS" min-width="80">
          <template #default="{ row }">
            <span :style="{ color: row.roas >= 2 ? '#22c55e' : row.roas >= 1 ? '#f59e0b' : '#ef4444', fontWeight: 'bold' }">
              {{ row.roas }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="$router.push(`/ads/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 商品推广排行 -->
    <el-card>
      <template #header>商品推广排行</template>
      <el-table ref="productTableRef" :data="productStats" stripe row-key="nm_id" @expand-change="onProductExpand" @row-click="onProductRowClick" style="cursor: pointer">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div style="padding: 8px 16px 8px 60px">
              <div v-if="row._campaignsLoading" style="color: var(--ts-text-muted); padding: 8px 0">加载中...</div>
              <div v-else-if="!row._campaigns || row._campaigns.length === 0" style="color: var(--ts-text-muted); padding: 8px 0">暂无关联广告活动</div>
              <el-table v-else :data="row._campaigns" size="small" :show-header="true" style="width: 100%">
                <el-table-column prop="name" label="活动名称" min-width="160" />
                <el-table-column prop="wb_advert_id" label="活动ID" min-width="100" />
                <el-table-column label="状态" min-width="70">
                  <template #default="{ row: c }">
                    <span :style="{ color: c.status === 7 ? '#22c55e' : '#64748b' }">
                      {{ c.status === 7 ? '进行中' : '已暂停' }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="花费" min-width="90">
                  <template #default="{ row: c }">₽{{ Math.round(c.spend)?.toLocaleString() }}</template>
                </el-table-column>
                <el-table-column label="展示" min-width="80">
                  <template #default="{ row: c }">{{ c.views?.toLocaleString() }}</template>
                </el-table-column>
                <el-table-column label="点击" min-width="70">
                  <template #default="{ row: c }">{{ c.clicks?.toLocaleString() }}</template>
                </el-table-column>
                <el-table-column label="订单" min-width="60">
                  <template #default="{ row: c }">{{ c.orders }}</template>
                </el-table-column>
                <el-table-column label="订单金额" min-width="90">
                  <template #default="{ row: c }">₽{{ Math.round(c.order_amount)?.toLocaleString() }}</template>
                </el-table-column>
                <el-table-column label="ROAS" min-width="70">
                  <template #default="{ row: c }">
                    <span :style="{ color: c.roas >= 2 ? '#22c55e' : c.roas >= 1 ? '#f59e0b' : '#ef4444', fontWeight: 'bold' }">
                      {{ c.roas }}
                    </span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="商品" min-width="200">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 8px">
              <el-image v-if="row.image_url" :src="row.image_url" style="width: 60px; height: 80px; border-radius: 6px; flex-shrink: 0" fit="cover" :preview-src-list="[row.image_url]" preview-teleported>
                <template #error><span style="color: #ccc; font-size: 12px">无图</span></template>
              </el-image>
              <span>{{ row.product_name || '-' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="sku" label="产品SKU" min-width="120" />
        <el-table-column prop="total_spend" label="花费" min-width="100">
          <template #default="{ row }">₽{{ Math.round(row.total_spend)?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="total_views" label="展示" min-width="90">
          <template #default="{ row }">{{ row.total_views?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="total_clicks" label="点击" min-width="80">
          <template #default="{ row }">{{ row.total_clicks?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="total_orders" label="订单" min-width="70" />
        <el-table-column prop="total_order_amount" label="订单金额" min-width="100">
          <template #default="{ row }">₽{{ Math.round(row.total_order_amount)?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="roas" label="ROAS" min-width="80">
          <template #default="{ row }">
            <span :style="{ color: row.roas >= 2 ? '#22c55e' : row.roas >= 1 ? '#f59e0b' : '#ef4444', fontWeight: 'bold' }">
              {{ row.roas }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="overall_orders" label="总订单" min-width="70" />
        <el-table-column prop="overall_order_amount" label="总订单金额" min-width="100">
          <template #default="{ row }">₽{{ Math.round(row.overall_order_amount)?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="overall_roas" label="总ROAS" min-width="80">
          <template #default="{ row }">
            <span :style="{ color: row.overall_roas >= 2 ? '#3b82f6' : row.overall_roas >= 1 ? '#f59e0b' : '#ef4444', fontWeight: 'bold' }">
              {{ row.overall_roas }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import api from '../api'

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent])

const overview = ref({})
const campaigns = ref([])
const productStats = ref([])
const dailyStats = ref([])
const productTableRef = ref(null)
const expandedProductRows = new Set()

function onProductRowClick(row) {
  if (expandedProductRows.has(row.nm_id)) {
    productTableRef.value.toggleRowExpansion(row, false)
    expandedProductRows.delete(row.nm_id)
  } else {
    productTableRef.value.toggleRowExpansion(row, true)
    expandedProductRows.add(row.nm_id)
  }
}

async function onProductExpand(row, expandedRows) {
  if (!expandedRows.includes(row)) { expandedProductRows.delete(row.nm_id); return }
  expandedProductRows.add(row.nm_id)
  if (row._campaigns) return // already loaded
  row._campaignsLoading = true
  try {
    const params = { date_from: currentFrom, date_to: currentTo }
    if (shopId.value) params.shop_id = shopId.value
    const res = await api.get(`/api/ads/product-campaigns/${row.nm_id}`, { params })
    row._campaigns = res.data
  } catch (e) {
    row._campaigns = []
  }
  row._campaignsLoading = false
}
const shops = ref([])
const shopId = ref(null)
const dateRange = ref(null)
const activePreset = ref('近7天')
const campaignStatus = ref(7) // 默认显示"进行中"
const campaignStatusFilters = [
  { label: '进行中', value: 7 },
  { label: '已暂停', value: 9 },
  { label: '全部', value: null },
]

const today = new Date()
function fmt(d) { return d.toISOString().slice(0, 10) }
function addDays(d, n) { const r = new Date(d); r.setDate(r.getDate() + n); return r }

const presets = [
  { label: '今日', from: fmt(today), to: fmt(today) },
  { label: '昨日', from: fmt(addDays(today, -1)), to: fmt(addDays(today, -1)) },
  { label: '近7天', from: fmt(addDays(today, -6)), to: fmt(today) },
  { label: '近30天', from: fmt(addDays(today, -29)), to: fmt(today) },
]

let currentFrom = presets[2].from
let currentTo = presets[2].to

function applyPreset(preset) {
  activePreset.value = preset.label
  currentFrom = preset.from
  currentTo = preset.to
  dateRange.value = null
  fetchAll()
}

function onDateChange(val) {
  if (val && val.length === 2) {
    activePreset.value = ''
    currentFrom = val[0]
    currentTo = val[1]
    fetchAll()
  }
}

function fmtKpi(value, prefix) {
  if (value == null) return '-'
  if (prefix === '₽') return '₽' + Math.round(value).toLocaleString()
  if (typeof value === 'number' && value % 1 !== 0 && !prefix) return value.toFixed(2)
  return (prefix || '') + value.toLocaleString()
}

const kpis = computed(() => [
  { label: '推广花费', value: overview.value.total_spend, prefix: '₽' },
  { label: '展示量', value: overview.value.total_views, prefix: '' },
  { label: '点击量', value: overview.value.total_clicks, prefix: '' },
  { label: '推广订单', value: overview.value.total_orders, prefix: '' },
  { label: 'ROAS', value: overview.value.roas, prefix: '', color: '#22c55e' },
  { label: '总订单', value: overview.value.overall_orders, prefix: '' },
  { label: '总订单金额', value: overview.value.overall_order_amount, prefix: '₽' },
  { label: '总ROAS', value: overview.value.overall_roas, prefix: '', color: '#3b82f6' },
])

const TYPE_MAP = { 5: '自动', 6: '搜索', 7: '卡片', 8: '推荐', 9: '搜索+推荐' }
const TYPE_TAG = { 5: 'success', 6: '', 7: 'warning', 8: '', 9: 'info' }
const STATUS_MAP = { 4: '准备中', 7: '进行中', 8: '审核中', 9: '已暂停', 11: '已暂停' }
const STATUS_COLOR = { 4: '#64748b', 7: '#22c55e', 8: '#f59e0b', 9: '#64748b', 11: '#64748b' }

function typeLabel(t) { return TYPE_MAP[t] || t }
function typeTagType(t) { return TYPE_TAG[t] || '' }
function statusLabel(s) { return STATUS_MAP[s] || s }
function statusColor(s) { return STATUS_COLOR[s] || '#606266' }

const chartOption = computed(() => {
  const byDate = {}
  for (const s of dailyStats.value) {
    const d = s.date
    if (!byDate[d]) byDate[d] = { spend: 0, order_amount: 0 }
    byDate[d].spend += s.spend
    byDate[d].order_amount += s.order_amount
  }
  const dates = Object.keys(byDate).sort()
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#ffffff',
      borderColor: '#e5e7eb',
      textStyle: { color: '#1e293b', fontFamily: 'Plus Jakarta Sans' },
    },
    legend: { data: ['花费', '订单金额'], bottom: 0, textStyle: { color: '#64748b' } },
    grid: { left: 50, right: 30, bottom: 40, top: 40 },
    xAxis: {
      type: 'category', data: dates,
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
      axisLabel: { color: '#94a3b8' },
    },
    series: [
      { name: '花费', type: 'bar', data: dates.map(d => byDate[d].spend.toFixed(2)), itemStyle: { color: '#3b82f6' } },
      { name: '订单金额', type: 'line', data: dates.map(d => byDate[d].order_amount.toFixed(2)), itemStyle: { color: '#f59e0b' }, smooth: true },
    ],
  }
})

async function fetchAll() {
  try {
    const params = { date_from: currentFrom, date_to: currentTo }
    if (shopId.value) params.shop_id = shopId.value
    const campParams = { ...params }
    if (campaignStatus.value !== null) campParams.status = campaignStatus.value
    // Fetch all campaigns (unfiltered) for trend chart, and filtered campaigns for table
    const [ovRes, campRes, allCampRes, prodRes] = await Promise.all([
      api.get('/api/ads/overview', { params }),
      api.get('/api/ads/campaigns', { params: campParams }),
      api.get('/api/ads/campaigns', { params }),
      api.get('/api/ads/product-stats', { params }),
    ])
    overview.value = ovRes.data
    campaigns.value = campRes.data
    productStats.value = prodRes.data

    // Use ALL campaigns' stats for trend chart (not just status-filtered ones)
    const allStats = []
    for (const c of allCampRes.data) {
      try {
        const res = await api.get(`/api/ads/campaigns/${c.id}/stats`, { params })
        allStats.push(...res.data)
      } catch (e) { /* skip */ }
    }
    dailyStats.value = allStats
  } catch (e) {
    console.error('Fetch ads data error:', e)
    ElMessage.error('数据加载失败')
  }
}

onMounted(async () => {
  try {
    const { data } = await api.get('/api/shops')
    shops.value = data
  } catch (e) { /* ignore */ }
  fetchAll()
})
</script>

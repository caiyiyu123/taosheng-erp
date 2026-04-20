<template>
  <div class="ts-dashboard">
    <!-- 今日 / 昨日概览 -->
    <div class="ts-section-label">订单概览</div>
    <el-row :gutter="16" class="ts-stat-row">
      <el-col :span="6">
        <div class="ts-stat-card ts-animate-in">
          <div class="ts-stat-card-inner">
            <div class="ts-stat-label">今日订单</div>
            <div class="ts-stat-value">{{ stats.today_orders }}</div>
          </div>
          <div class="ts-stat-indicator ts-stat-blue"></div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="ts-stat-card ts-animate-in">
          <div class="ts-stat-card-inner">
            <div class="ts-stat-label">今日销售额</div>
            <div class="ts-stat-value">₽{{ Math.round(stats.today_sales)?.toLocaleString() }}</div>
          </div>
          <div class="ts-stat-indicator ts-stat-gold"></div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="ts-stat-card ts-animate-in">
          <div class="ts-stat-card-inner">
            <div class="ts-stat-label">昨日订单</div>
            <div class="ts-stat-value">{{ stats.yesterday_orders }}</div>
          </div>
          <div class="ts-stat-indicator ts-stat-blue"></div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="ts-stat-card ts-animate-in">
          <div class="ts-stat-card-inner">
            <div class="ts-stat-label">昨日销售额</div>
            <div class="ts-stat-value">₽{{ Math.round(stats.yesterday_sales)?.toLocaleString() }}</div>
          </div>
          <div class="ts-stat-indicator ts-stat-gold"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 第二行 -->
    <el-row :gutter="16" class="ts-stat-row">
      <el-col :span="5">
        <div class="ts-stat-card ts-animate-in">
          <div class="ts-stat-card-inner">
            <div class="ts-stat-label">近30天订单</div>
            <div class="ts-stat-value">{{ stats.days30_orders }}</div>
          </div>
          <div class="ts-stat-indicator ts-stat-blue"></div>
        </div>
      </el-col>
      <el-col :span="5">
        <div class="ts-stat-card ts-animate-in">
          <div class="ts-stat-card-inner">
            <div class="ts-stat-label">近30天销售额</div>
            <div class="ts-stat-value">₽{{ Math.round(stats.days30_sales)?.toLocaleString() }}</div>
          </div>
          <div class="ts-stat-indicator ts-stat-gold"></div>
        </div>
      </el-col>
      <el-col :span="5">
        <div class="ts-stat-card ts-animate-in">
          <div class="ts-stat-card-inner">
            <div class="ts-stat-label">待发货</div>
            <div class="ts-stat-value ts-gold">{{ stats.pending_shipment }}</div>
          </div>
          <div class="ts-stat-indicator ts-stat-orange"></div>
        </div>
      </el-col>
      <el-col :span="5">
        <div class="ts-stat-card ts-animate-in">
          <div class="ts-stat-card-inner">
            <div class="ts-stat-label">配送中</div>
            <div class="ts-stat-value ts-teal">{{ stats.in_transit_count }}</div>
          </div>
          <div class="ts-stat-indicator ts-stat-teal"></div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="ts-stat-card ts-animate-in">
          <div class="ts-stat-card-inner">
            <div class="ts-stat-label">低库存预警</div>
            <div class="ts-stat-value ts-danger">{{ stats.low_stock_count }}</div>
          </div>
          <div class="ts-stat-indicator ts-stat-red"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 近30天趋势图 -->
    <el-card class="ts-chart-card">
      <template #header>
        <span class="ts-chart-title">近30天订单趋势</span>
      </template>
      <v-chart :option="chartOption" style="height: 320px" autoresize />
    </el-card>

    <!-- 店铺看板 -->
    <el-row :gutter="16" v-loading="loading.shops" style="margin-top: 24px; margin-bottom: 16px">
      <el-col :span="4" v-for="shop in shopCards" :key="shop.id">
        <div
          class="ts-stat-card ts-shop-card"
          :class="{ 'ts-shop-card-active': currentShop && currentShop.id === shop.id }"
          @click="openShop(shop)"
        >
          <div class="ts-shop-name">{{ shop.name }}</div>
          <div class="ts-shop-metric">
            <span class="ts-shop-metric-label">今日订单</span>
            <span class="ts-shop-metric-value">{{ shop.today_orders }}</span>
          </div>
          <div class="ts-shop-metric">
            <span class="ts-shop-metric-label">今日销售额</span>
            <span class="ts-shop-metric-value">₽{{ Math.round(shop.today_sales).toLocaleString() }}</span>
          </div>
          <div class="ts-shop-metric">
            <span class="ts-shop-metric-label">近30天订单</span>
            <span class="ts-shop-metric-value">{{ shop.last_30d_orders }}</span>
          </div>
          <div class="ts-shop-metric">
            <span class="ts-shop-metric-label">近30天销售额</span>
            <span class="ts-shop-metric-value">₽{{ Math.round(shop.last_30d_sales).toLocaleString() }}</span>
          </div>
          <div class="ts-stat-indicator ts-stat-blue"></div>
        </div>
      </el-col>
      <el-col v-if="!loading.shops && shopCards.length === 0" :span="24">
        <el-empty description="暂无店铺数据" />
      </el-col>
    </el-row>

    <!-- 商品销量排行 -->
    <div v-if="viewMode === 'products'" v-loading="loading.products">
      <el-table
        ref="productTableRef"
        :data="productList"
        stripe
        row-key="nm_id"
        max-height="640"
        :fit="false"
        :default-sort="{ prop: 'today_orders', order: 'descending' }"
        @expand-change="onExpandChange"
        @row-click="toggleRowExpand"
        class="ts-product-table"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="ts-expand-chart" v-loading="productDailyLoading[row.nm_id]">
              <v-chart
                v-if="productDaily[row.nm_id] && productDaily[row.nm_id].length > 0"
                :option="getDailyChartOption(row.nm_id)"
                style="height: 220px"
                autoresize
              />
              <el-empty
                v-else-if="!productDailyLoading[row.nm_id]"
                description="暂无近30天数据"
                :image-size="60"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="图片" width="76" align="center">
          <template #default="{ row }">
            <el-image
              v-if="row.image_url"
              :src="row.image_url"
              fit="cover"
              style="width: 48px; height: 48px; border-radius: 4px"
              lazy
              preview-teleported
              :preview-src-list="[row.image_url]"
            />
            <div v-else class="ts-product-img-placeholder">—</div>
          </template>
        </el-table-column>
        <el-table-column prop="sku" label="SKU" width="150" show-overflow-tooltip />
        <el-table-column label="产品名" width="300">
          <template #default="{ row }">
            <div class="ts-product-name">
              <div class="ts-product-name-ru" :title="row.product_name">{{ truncate(row.product_name, 35) }}</div>
              <div
                v-if="translatedNames[row.product_name]"
                class="ts-product-name-zh"
                :title="translatedNames[row.product_name]"
              >{{ translatedNames[row.product_name] }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="today_orders" label="今日订单" width="100" sortable align="center" />
        <el-table-column prop="yesterday_orders" label="昨日订单" width="100" sortable align="center" />
        <el-table-column prop="last_7d_orders" label="近7天订单" width="110" sortable align="center" />
        <el-table-column prop="last_30d_orders" label="近30天订单" width="120" sortable align="center" />
      </el-table>
      <el-empty v-if="!loading.products && productList.length === 0" description="该店铺暂无商品订单数据" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import api from '../api'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent])

const stats = ref({
  today_orders: 0, today_sales: 0, yesterday_orders: 0, yesterday_sales: 0,
  pending_shipment: 0, in_transit_count: 0,
  low_stock_count: 0, days30_orders: 0, days30_sales: 0, daily_trend: [],
})

const viewMode = ref('shops')         // 'shops' | 'products'
const currentShop = ref(null)         // { id, name }

const shopCards = ref([])
const productList = ref([])
const productDaily = ref({})          // { [nm_id]: [{ date, orders }] }
const productDailyLoading = ref({})   // { [nm_id]: boolean }
const translatedNames = ref({})       // { [ru_text]: zh_text }
const loading = ref({ shops: false, products: false })
const productTableRef = ref(null)
const chartOptionCache = new Map()    // { [nm_id]: echartsOption }

async function fetchShopCards() {
  loading.value.shops = true
  try {
    const { data } = await api.get('/api/dashboard/shops')
    shopCards.value = data.shops
  } catch (e) {
    console.error('shops error', e)
    ElMessage.error('店铺数据加载失败')
  } finally {
    loading.value.shops = false
  }
}

function truncate(text, n) {
  if (!text) return ''
  return text.length > n ? text.slice(0, n) + '…' : text
}

function moscowToday() {
  return new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString().slice(0, 10)
}

async function openShop(shop) {
  currentShop.value = { id: shop.id, name: shop.name }
  productList.value = []
  productDaily.value = {}
  productDailyLoading.value = {}
  chartOptionCache.clear()
  viewMode.value = 'products'
  loading.value.products = true
  try {
    const { data } = await api.get(`/api/dashboard/shops/${shop.id}/products`)
    productList.value = data.products
    translateProductNames(data.products.map(p => p.product_name))
  } catch (e) {
    const msg = e?.response?.status === 403 ? '无权访问该店铺' : '商品数据加载失败'
    ElMessage.error(msg)
    viewMode.value = 'shops'
  } finally {
    loading.value.products = false
  }
}

async function translateProductNames(names) {
  const needs = [...new Set(names.filter(n => n && !translatedNames.value[n]))]
  if (!needs.length) return
  try {
    const { data } = await api.post('/api/dashboard/translate-batch', { texts: needs })
    translatedNames.value = { ...translatedNames.value, ...data.translations }
  } catch (e) {
    console.warn('translate error', e)
  }
}

function toggleRowExpand(row, column, event) {
  // 点击展开列箭头时，el-table 自己会处理，避免再次 toggle 抵消
  if (column?.type === 'expand') return
  // 点击图片/预览层时，不触发展开
  if (event?.target?.closest('.el-image-viewer__wrapper, .el-image__preview')) return
  productTableRef.value?.toggleRowExpansion(row)
}

async function onExpandChange(row, expandedRows) {
  const isExpanded = Array.isArray(expandedRows)
    ? expandedRows.some(r => r.nm_id === row.nm_id)
    : !!expandedRows
  if (!isExpanded) return
  if (productDaily.value[row.nm_id]) return
  await loadProductDaily(row.nm_id)
}

async function loadProductDaily(nmId) {
  if (!currentShop.value) return
  productDailyLoading.value = { ...productDailyLoading.value, [nmId]: true }
  try {
    const { data } = await api.get(
      `/api/dashboard/shops/${currentShop.value.id}/products/${nmId}/daily`,
      { params: { end_date: moscowToday(), days: 30 } },
    )
    productDaily.value = { ...productDaily.value, [nmId]: data.daily }
    chartOptionCache.delete(nmId)
  } catch (e) {
    const msg = e?.response?.status === 403 ? '无权访问该店铺' : '每日数据加载失败'
    ElMessage.error(msg)
  } finally {
    productDailyLoading.value = { ...productDailyLoading.value, [nmId]: false }
  }
}

function getDailyChartOption(nmId) {
  if (chartOptionCache.has(nmId)) return chartOptionCache.get(nmId)
  const data = productDaily.value[nmId] || []
  const dates = data.map(d => d.date.slice(5)) // MM-DD
  const orders = data.map(d => d.orders)
  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const p = params[0]
        const full = data[p.dataIndex]?.date || p.axisValue
        return `${full}<br/>订单数：<b>${p.data}</b>`
      },
    },
    grid: { left: 16, right: 16, top: 32, bottom: 28, containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      show: false,
    },
    series: [{
      type: 'line',
      data: orders,
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      itemStyle: { color: '#3b82f6' },
      lineStyle: { width: 2.5, color: '#3b82f6' },
      label: {
        show: true,
        position: 'top',
        color: '#1e293b',
        fontSize: 11,
        fontWeight: 600,
      },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(59,130,246,0.25)' },
            { offset: 1, color: 'rgba(59,130,246,0)' },
          ],
        },
      },
    }],
  }
  chartOptionCache.set(nmId, option)
  return option
}

const chartOption = computed(() => {
  const trend = stats.value.daily_trend || []
  const dates = trend.map(d => d.date.slice(5)) // MM-DD
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#ffffff',
      borderColor: '#e5e7eb',
      textStyle: { color: '#1e293b', fontFamily: 'Plus Jakarta Sans' },
      formatter(params) {
        const idx = params[0].dataIndex
        const item = trend[idx]
        return `<b>${item.date}</b><br/>` +
          `订单数：<b>${item.orders}</b><br/>` +
          `订单金额：<b>₽${Math.round(item.sales).toLocaleString()}</b>`
      },
    },
    legend: {
      data: ['订单数', '订单金额(₽)'],
      bottom: 0,
      textStyle: { color: '#64748b', fontFamily: 'Plus Jakarta Sans' },
    },
    grid: { left: 50, right: 60, bottom: 40, top: 20 },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisLabel: { color: '#94a3b8', fontFamily: 'Plus Jakarta Sans' },
    },
    yAxis: [
      {
        type: 'value', name: '订单数', position: 'left', minInterval: 1,
        nameTextStyle: { color: '#94a3b8' },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
        axisLabel: { color: '#94a3b8' },
      },
      {
        type: 'value', name: '金额(₽)', position: 'right',
        nameTextStyle: { color: '#94a3b8' },
        axisLine: { show: false },
        splitLine: { show: false },
        axisLabel: { color: '#64748b' },
      },
    ],
    series: [
      {
        name: '订单数',
        type: 'line',
        yAxisIndex: 0,
        data: trend.map(d => d.orders),
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#3b82f6' },
        lineStyle: { width: 2.5 },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(59,130,246,0.2)' },
              { offset: 1, color: 'rgba(59,130,246,0)' },
            ],
          },
        },
      },
      {
        name: '订单金额(₽)',
        type: 'line',
        yAxisIndex: 1,
        data: trend.map(d => Math.round(d.sales)),
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#f59e0b' },
        lineStyle: { width: 2.5 },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(245,158,11,0.2)' },
              { offset: 1, color: 'rgba(245,158,11,0)' },
            ],
          },
        },
      },
    ],
  }
})

onMounted(async () => {
  try {
    const { data } = await api.get('/api/dashboard/stats')
    stats.value = data
    await fetchShopCards()
  } catch (e) {
    console.error('Dashboard stats error:', e)
    ElMessage.error('数据加载失败')
  }
})
</script>

<style scoped>
.ts-dashboard {
  animation: ts-fade-in 0.4s ease both;
}

.ts-section-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--ts-text-muted);
  margin-bottom: 12px;
}

.ts-stat-row {
  margin-bottom: 24px;
}

.ts-stat-card {
  background: #ffffff;
  border: 1px solid var(--ts-glass-border);
  border-radius: var(--ts-radius-md);
  padding: 20px 22px;
  position: relative;
  overflow: hidden;
  transition: all var(--ts-duration) var(--ts-ease);
  cursor: default;
  box-shadow: var(--ts-shadow-sm);
}
.ts-stat-card:hover {
  border-color: rgba(0, 0, 0, 0.1);
  box-shadow: var(--ts-shadow-md);
  transform: translateY(-2px);
}
.ts-stat-card-inner {
  position: relative;
  z-index: 1;
}

.ts-stat-indicator {
  position: absolute;
  top: 0;
  right: 0;
  width: 4px;
  height: 100%;
  opacity: 0.6;
  border-radius: 0 var(--ts-radius-md) var(--ts-radius-md) 0;
}
.ts-stat-blue { background: linear-gradient(135deg, #3b82f6, #60a5fa); }
.ts-stat-gold { background: linear-gradient(135deg, #f59e0b, #fbbf24); }
.ts-stat-orange { background: linear-gradient(135deg, #f97316, #fb923c); }
.ts-stat-teal { background: linear-gradient(135deg, #14b8a6, #2dd4bf); }
.ts-stat-red { background: linear-gradient(135deg, #ef4444, #f87171); }

.ts-chart-card {
  margin-top: 4px;
}
.ts-chart-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--ts-text-heading);
}

.ts-shop-card {
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.ts-shop-card-active {
  border-color: #2563eb;
  border-width: 2px;
  padding: 11px 13px;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.35), 0 6px 18px rgba(37, 99, 235, 0.18);
  background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%);
}
.ts-shop-card-active .ts-shop-name {
  color: #1d4ed8;
}
.ts-shop-name {
  font-size: 13px;
  font-weight: 800;
  text-align: center;
  color: var(--ts-text-heading);
  margin-bottom: 4px;
}
.ts-shop-metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11.5px;
  line-height: 1.4;
}
.ts-shop-metric-label {
  color: var(--ts-text-muted);
}
.ts-shop-metric-value {
  font-weight: 600;
  color: var(--ts-text-heading);
}

.ts-product-img-placeholder {
  width: 48px;
  height: 48px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #94a3b8;
  font-size: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ts-product-table :deep(.el-table__row) {
  cursor: pointer;
}

.ts-expand-chart {
  padding: 12px 24px 8px;
  background: #fafbfc;
}

.ts-product-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.35;
}
.ts-product-name-ru {
  color: var(--ts-text-heading);
  font-weight: 600;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ts-product-name-zh {
  color: var(--ts-text-muted);
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

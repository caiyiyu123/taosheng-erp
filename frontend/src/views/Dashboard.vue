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
</style>

<template>
  <div>
    <!-- 今日概览 -->
    <el-row :gutter="16" style="margin-bottom: 20px">
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="color: #999; font-size: 14px">今日订单</div>
          <div style="font-size: 28px; font-weight: bold">{{ stats.today_orders }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="color: #999; font-size: 14px">今日销售额</div>
          <div style="font-size: 28px; font-weight: bold">¥ {{ stats.today_sales?.toLocaleString() }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="color: #999; font-size: 14px">待发货</div>
          <div style="font-size: 28px; font-weight: bold; color: #f57c00">{{ stats.pending_shipment }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="color: #999; font-size: 14px">配送中</div>
          <div style="font-size: 28px; font-weight: bold; color: #1976d2">{{ stats.in_transit_count }}</div>
        </el-card>
      </el-col>
    </el-row>
    <!-- 累计数据 + 库存预警 -->
    <el-row :gutter="16" style="margin-bottom: 20px">
      <el-col :span="8">
        <el-card shadow="hover">
          <div style="color: #999; font-size: 14px">累计订单</div>
          <div style="font-size: 28px; font-weight: bold">{{ stats.total_orders }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <div style="color: #999; font-size: 14px">累计销售额</div>
          <div style="font-size: 28px; font-weight: bold">¥ {{ stats.total_sales?.toLocaleString() }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <div style="color: #999; font-size: 14px">低库存预警</div>
          <div style="font-size: 28px; font-weight: bold; color: #c62828">{{ stats.low_stock_count }}</div>
        </el-card>
      </el-col>
    </el-row>
    <!-- 最近订单 -->
    <el-card>
      <template #header>最近订单</template>
      <el-table :data="stats.recent_orders" stripe>
        <el-table-column prop="wb_order_id" label="订单号" min-width="130" />
        <el-table-column prop="order_type" label="类型" min-width="70">
          <template #default="{ row }">
            <el-tag :type="row.order_type === 'FBS' ? 'success' : 'primary'" size="small">{{ row.order_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_price" label="金额" min-width="100">
          <template #default="{ row }">¥ {{ row.total_price?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" min-width="80">
          <template #default="{ row }">
            <span :style="{ color: statusColor(row.status), fontWeight: 'bold' }">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="下单时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const stats = ref({
  today_orders: 0, today_sales: 0, pending_shipment: 0, in_transit_count: 0,
  low_stock_count: 0, total_orders: 0, total_sales: 0, recent_orders: [],
})

const STATUS_MAP = {
  pending: '待发货', in_transit: '配送中',
  completed: '已完成', cancelled: '已取消', rejected: '已拒收', returned: '已退货',
}
const STATUS_COLOR = {
  pending: '#606266', in_transit: '#409eff', completed: '#67c23a',
  cancelled: '#e6a23c', rejected: '#f56c6c', returned: '#909399',
}

function statusLabel(status) { return STATUS_MAP[status] || status }
function statusColor(status) { return STATUS_COLOR[status] || '#606266' }

function formatTime(dt) {
  if (!dt) return ''
  const utcDt = String(dt).endsWith('Z') ? dt : dt + 'Z'
  return new Date(utcDt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}

onMounted(async () => {
  const { data } = await api.get('/api/dashboard/stats')
  stats.value = data
})
</script>

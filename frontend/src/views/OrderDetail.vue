<template>
  <div v-if="order">
    <el-page-header @back="$router.back()">
      <template #content>订单 {{ order.wb_order_id }}</template>
    </el-page-header>
    <el-descriptions :column="3" border style="margin-top: 20px">
      <el-descriptions-item label="订单号">{{ order.wb_order_id }}</el-descriptions-item>
      <el-descriptions-item label="类型">
        <el-tag :type="order.order_type === 'FBS' ? 'success' : 'primary'">{{ order.order_type }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="状态">{{ order.status }}</el-descriptions-item>
      <el-descriptions-item label="金额">¥ {{ order.total_price?.toLocaleString() }}</el-descriptions-item>
      <el-descriptions-item label="仓库">{{ order.warehouse_name }}</el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ order.created_at }}</el-descriptions-item>
    </el-descriptions>
    <el-card style="margin-top: 20px">
      <template #header>商品明细</template>
      <el-table :data="order.items">
        <el-table-column prop="product_name" label="商品名" />
        <el-table-column prop="sku" label="产品SKU" />
        <el-table-column prop="quantity" label="数量" />
        <el-table-column prop="price" label="售价">
          <template #default="{ row }">¥ {{ row.price }}</template>
        </el-table-column>
        <el-table-column prop="commission" label="佣金">
          <template #default="{ row }">¥ {{ row.commission }}</template>
        </el-table-column>
        <el-table-column prop="logistics_cost" label="物流费">
          <template #default="{ row }">¥ {{ row.logistics_cost }}</template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-card style="margin-top: 20px">
      <template #header>状态时间线</template>
      <el-timeline>
        <el-timeline-item v-for="log in order.status_logs" :key="log.id" :timestamp="log.changed_at">
          {{ log.status }} <span v-if="log.note" style="color: var(--ts-text-muted)">— {{ log.note }}</span>
        </el-timeline-item>
      </el-timeline>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

const route = useRoute()
const order = ref(null)

onMounted(async () => {
  try {
    const { data } = await api.get(`/api/orders/${route.params.id}`)
    order.value = data
  } catch (e) {
    console.error('Fetch order detail error:', e)
    ElMessage.error('数据加载失败')
  }
})
</script>

<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center">
        <span>库存管理</span>
        <el-switch v-model="showLowOnly" active-text="仅低库存" @change="fetchInventory" />
      </div>
    </template>
    <el-table :data="inventory" stripe>
      <el-table-column prop="product_name" label="商品名" />
      <el-table-column prop="sku" label="产品SKU" />
      <el-table-column prop="stock_fbs" label="FBS库存" />
      <el-table-column prop="stock_fbw" label="FBW库存" />
      <el-table-column label="总库存">
        <template #default="{ row }">{{ row.stock_fbs + row.stock_fbw }}</template>
      </el-table-column>
      <el-table-column prop="low_stock_threshold" label="预警阈值" />
      <el-table-column label="状态">
        <template #default="{ row }">
          <el-tag v-if="(row.stock_fbs + row.stock_fbw) < row.low_stock_threshold" type="danger" size="small">低库存</el-tag>
          <el-tag v-else type="success" size="small">正常</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const inventory = ref([])
const showLowOnly = ref(false)

async function fetchInventory() {
  try {
    const url = showLowOnly.value ? '/api/inventory/low-stock' : '/api/inventory'
    const { data } = await api.get(url)
    inventory.value = data
  } catch (e) {
    console.error('Fetch inventory error:', e)
    ElMessage.error('数据加载失败')
  }
}

onMounted(fetchInventory)
</script>

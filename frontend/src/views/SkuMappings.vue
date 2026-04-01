<template>
  <div>
    <el-page-header @back="$router.back()">
      <template #content>SKU 关联管理（产品SKU → 商品SKU）</template>
    </el-page-header>
    <el-card style="margin-top: 20px">
      <el-table :data="mappings" stripe>
        <el-table-column prop="wb_product_name" label="WB商品名称" />
        <el-table-column prop="shop_sku" label="产品SKU" />
        <el-table-column prop="wb_barcode" label="条码" />
        <el-table-column label="关联商品SKU" width="250">
          <template #default="{ row }">
            <el-input v-model="row._input_sku" placeholder="输入商品SKU" @blur="linkSku(row)" @keyup.enter="linkSku(row)">
              <template #suffix>
                <el-icon v-if="row.product_id" style="color: #67c23a"><Check /></el-icon>
              </template>
            </el-input>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.product_id ? 'success' : 'warning'" size="small">
              {{ row.product_id ? '已关联' : '未关联' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check } from '@element-plus/icons-vue'
import api from '../api'

const route = useRoute()
const shopId = route.params.id
const mappings = ref([])

async function fetchMappings() {
  const { data } = await api.get(`/api/shops/${shopId}/sku-mappings`)
  const products = (await api.get('/api/products')).data
  const skuMap = {}
  products.forEach(p => { skuMap[p.id] = p.sku })
  mappings.value = data.map(m => ({
    ...m,
    _input_sku: m.product_id && skuMap[m.product_id] ? skuMap[m.product_id] : ''
  }))
}

async function linkSku(row) {
  try {
    await api.put(`/api/sku-mappings/${row.id}`, { product_sku: row._input_sku || '' })
    ElMessage.success(row._input_sku ? '关联成功' : '已取消关联')
    fetchMappings()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '关联失败')
  }
}

onMounted(fetchMappings)
</script>

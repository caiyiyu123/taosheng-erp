<template>
  <div>
    <el-page-header @back="$router.back()">
      <template #content>SKU 关联管理（产品SKU → 商品SKU）</template>
    </el-page-header>
    <el-card style="margin-top: 20px">
      <el-table :data="mappings" stripe>
        <el-table-column label="图片" width="80" align="center">
          <template #default="{ row }">
            <el-image v-if="row.wb_image_url" :src="row.wb_image_url" style="width: 50px; height: 50px; display: block" fit="contain" :preview-src-list="[row.wb_image_url]" preview-teleported />
            <span v-else style="color: #ccc">无图</span>
          </template>
        </el-table-column>
        <el-table-column prop="wb_product_name" label="WB产品名称" />
        <el-table-column prop="shop_sku" label="产品SKU" />
        <el-table-column prop="wb_barcode" label="条码" />
        <el-table-column label="关联商品SKU" width="300">
          <template #default="{ row }">
            <div style="display: flex; gap: 6px; align-items: center">
              <el-input v-model="row._input_sku" placeholder="输入商品SKU" size="small">
                <template #suffix>
                  <el-icon v-if="row.product_id" style="color: #67c23a"><Check /></el-icon>
                </template>
              </el-input>
              <el-popconfirm :title="row._input_sku ? `确认关联到 ${row._input_sku}？` : '确认取消关联？'" @confirm="linkSku(row)">
                <template #reference>
                  <el-button size="small" type="primary">确认</el-button>
                </template>
              </el-popconfirm>
            </div>
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
  try {
    const { data } = await api.get(`/api/shops/${shopId}/sku-mappings`)
    const products = (await api.get('/api/products')).data
    const skuMap = {}
    products.forEach(p => { skuMap[p.id] = p.sku })
    mappings.value = data.map(m => ({
      ...m,
      _input_sku: m.product_id && skuMap[m.product_id] ? skuMap[m.product_id] : ''
    }))
  } catch (e) {
    ElMessage.error('数据加载失败')
  }
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

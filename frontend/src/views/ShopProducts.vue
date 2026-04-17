<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px">
        <span>产品管理</span>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap">
          <el-select v-model="shopId" placeholder="全部店铺" clearable size="small" style="width: 150px" @change="fetchProducts">
            <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
          <el-input v-model="search" placeholder="搜索 SKU / 产品标题" clearable style="width: 220px" size="small"
            @keyup.enter="fetchProducts" @clear="fetchProducts">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-button type="primary" size="small" :loading="syncing" @click="syncProducts">
            {{ syncing ? '同步中...' : '同步产品' }}
          </el-button>
        </div>
      </div>
    </template>

    <el-table :data="products" stripe>
      <el-table-column label="图片" width="80">
        <template #default="{ row }">
          <el-image v-if="row.image_url" :src="row.image_url" style="width: 50px; height: 65px" fit="cover" lazy />
          <span v-else style="color: #ccc">无图</span>
        </template>
      </el-table-column>
      <el-table-column prop="shop_name" label="店铺" min-width="120" />
      <el-table-column prop="vendor_code" label="SKU" min-width="130" />
      <el-table-column label="关联SKU" min-width="120">
        <template #default="{ row }">
          <span v-if="row.mapped_sku">{{ row.mapped_sku }}</span>
          <span v-else style="color: #ccc">未关联</span>
        </template>
      </el-table-column>
      <el-table-column label="产品标题" min-width="220">
        <template #default="{ row }">
          <a v-if="row.nm_id" :href="'https://www.wildberries.ru/catalog/' + row.nm_id + '/detail.aspx'" target="_blank" style="color: #409eff; text-decoration: none">
            <el-tooltip v-if="row.title.length > 35" :content="row.title" placement="top">
              <span>{{ row.title.slice(0, 35) + '...' }}</span>
            </el-tooltip>
            <span v-else>{{ row.title }}</span>
          </a>
          <template v-else>
            <el-tooltip v-if="row.title.length > 35" :content="row.title" placement="top">
              <span>{{ row.title.slice(0, 35) + '...' }}</span>
            </el-tooltip>
            <span v-else>{{ row.title }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="价格(₽)" width="100" align="center">
        <template #default="{ row }">
          {{ row.price_rub > 0 ? '₽' + row.price_rub.toLocaleString() : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="价格(¥)" width="100" align="center">
        <template #default="{ row }">
          {{ row.price_cny > 0 ? '¥' + row.price_cny.toLocaleString() : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="FBS库存" width="90" align="center">
        <template #default="{ row }">
          <span :style="{ color: row.stock_fbs <= 0 ? '#f56c6c' : row.stock_fbs < 10 ? '#e6a23c' : '' }">
            {{ row.stock_fbs }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="FBW库存" width="90" align="center">
        <template #default="{ row }">
          <span :style="{ color: row.stock_fbw <= 0 ? '#f56c6c' : row.stock_fbw < 10 ? '#e6a23c' : '' }">
            {{ row.stock_fbw }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="评分" width="80" align="center">
        <template #default="{ row }">
          <span :style="{ color: row.rating >= 4.5 ? '#67c23a' : row.rating >= 4 ? '#e6a23c' : '#f56c6c', fontWeight: 'bold' }">
            {{ row.rating > 0 ? row.rating.toFixed(1) : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="评价数" width="80" align="center">
        <template #default="{ row }">
          {{ row.feedbacks_count > 0 ? row.feedbacks_count : '-' }}
        </template>
      </el-table-column>
    </el-table>

    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 16px">
      <span style="color: #999; font-size: 13px">共 {{ total }} 条</span>
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="fetchProducts"
      />
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import api from '../api'

const shops = ref([])
const products = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const shopId = ref(null)
const search = ref('')
const syncing = ref(false)
let syncPollTimer = null

async function fetchProducts() {
  try {
    const params = { page: page.value, page_size: pageSize }
    if (shopId.value) params.shop_id = shopId.value
    if (search.value) params.search = search.value
    const { data } = await api.get('/api/shop-products', { params })
    products.value = data.items
    total.value = data.total
  } catch (e) {
    console.error('Fetch products error:', e)
    ElMessage.error('数据加载失败')
  }
}

async function syncProducts() {
  syncing.value = true
  try {
    await api.post('/api/shop-products/sync')
    let polls = 0
    syncPollTimer = setInterval(async () => {
      if (++polls > 60) {
        clearInterval(syncPollTimer)
        syncPollTimer = null
        syncing.value = false
        ElMessage.warning('同步超时，请稍后重试')
        return
      }
      try {
        const { data } = await api.get('/api/shop-products/sync/status')
        if (data.status === 'done') {
          clearInterval(syncPollTimer)
          syncPollTimer = null
          syncing.value = false
          ElMessage.success(data.detail || '产品同步完成')
          fetchProducts()
        } else if (data.status === 'error') {
          clearInterval(syncPollTimer)
          syncPollTimer = null
          syncing.value = false
          ElMessage.error('同步失败: ' + (data.detail || '未知错误'))
        }
      } catch {}
    }, 2000)
  } catch {
    syncing.value = false
    ElMessage.error('同步请求失败')
  }
}

onMounted(async () => {
  try {
    const { data } = await api.get('/api/shops')
    shops.value = data
  } catch {}
  fetchProducts()
})

onBeforeUnmount(() => {
  if (syncPollTimer) {
    clearInterval(syncPollTimer)
    syncPollTimer = null
  }
})
</script>

<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center">
        <span>商品管理</span>
        <el-button type="primary" @click="openDialog()">添加商品</el-button>
      </div>
    </template>
    <el-table :data="products" stripe>
      <el-table-column prop="developer" label="开发员" width="90" />
      <el-table-column label="图片" width="80" align="center">
        <template #default="{ row }">
          <el-image v-if="row.image" :src="imageUrl(row.image)" style="width: 50px; height: 50px; display: block; cursor: pointer" fit="contain" :preview-src-list="[imageUrl(row.image)]" preview-teleported />
          <span v-else style="color: #ccc">无图</span>
        </template>
      </el-table-column>
      <el-table-column prop="sku" label="商品SKU" min-width="130" />
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column prop="purchase_price" label="采购价" align="center" min-width="90">
        <template #default="{ row }">¥ {{ row.purchase_price }}</template>
      </el-table-column>
      <el-table-column prop="weight" label="重量(kg)" align="center" min-width="80" />
      <el-table-column prop="length" label="长(cm)" align="center" min-width="70" />
      <el-table-column prop="width" label="宽(cm)" align="center" min-width="70" />
      <el-table-column prop="height" label="高(cm)" align="center" min-width="70" />
      <el-table-column label="密度" align="center" min-width="80">
        <template #default="{ row }">{{ calcDensity(row) }}</template>
      </el-table-column>
      <el-table-column label="装箱数" align="center" min-width="90">
        <template #default="{ row }">
          <el-input-number
            v-model="row.packing_qty"
            :min="0"
            :precision="0"
            :controls="false"
            size="small"
            style="width: 70px; font-size: 12px"
            @change="savePackingQty(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="头程运费(预估)" align="center" min-width="120">
        <template #default="{ row }">
          <span v-if="calcEstimatedShipping(row) !== '-'">¥ {{ calcEstimatedShipping(row) }}</span>
          <span v-else style="color: #ccc">-</span>
        </template>
      </el-table-column>
      <el-table-column label="头程运费(实际)" align="center" min-width="110">
        <template #default="{ row }">
          <span style="color: #606266; margin-right: 2px">¥</span>
          <el-input-number
            v-model="row.actual_shipping_cost"
            :min="0"
            :precision="2"
            :controls="false"
            size="small"
            style="width: 70px; font-size: 12px"
            @change="saveActualShipping(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="center">
        <template #default="{ row }">
          <el-button size="small" @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确定删除?" @confirm="deleteProduct(row.id)">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="showDialog" :title="form.id ? '编辑商品' : '添加商品'" width="500px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="开发员">
        <el-select v-model="form.developer" placeholder="选择开发员" clearable style="width: 100%">
          <el-option v-for="u in userNames" :key="u" :label="u" :value="u" />
        </el-select>
      </el-form-item>
      <el-form-item label="商品SKU"><el-input v-model="form.sku" /></el-form-item>
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="采购价"><el-input-number v-model="form.purchase_price" :min="0" :precision="1" :controls="false" /></el-form-item>
      <el-form-item label="重量(kg)"><el-input-number v-model="form.weight" :min="0" :precision="2" :step="0.01" :controls="false" /></el-form-item>
      <el-form-item label="长(cm)"><el-input-number v-model="form.length" :min="0" :controls="false" /></el-form-item>
      <el-form-item label="宽(cm)"><el-input-number v-model="form.width" :min="0" :controls="false" /></el-form-item>
      <el-form-item label="高(cm)"><el-input-number v-model="form.height" :min="0" :controls="false" /></el-form-item>
      <el-form-item label="装箱数"><el-input-number v-model="form.packing_qty" :min="0" :precision="0" :controls="false" /></el-form-item>
      <el-form-item label="商品图片">
        <ImageUploader ref="imgUploaderRef" :model-value="imagePreview" @file-change="onImageFile" @remove="onImageRemove" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showDialog = false">取消</el-button>
      <el-button type="primary" @click="saveProduct">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api, { imageUrl } from '../api'
import ImageUploader from '../components/ImageUploader.vue'

const products = ref([])
const userNames = ref([])
const shippingRates = ref([])
const usdToCny = ref(0)

function calcDensity(row) {
  const volume = (row.length || 0) * (row.width || 0) * (row.height || 0)
  if (!volume || !row.weight) return '-'
  return Math.round(row.weight * 1000000 / volume)
}

function calcEstimatedShipping(row) {
  const density = calcDensity(row)
  if (density === '-' || !shippingRates.value.length || !usdToCny.value) return '-'
  const rate = shippingRates.value.find(r => density >= r.density_min && density <= r.density_max)
  if (!rate) return '-'
  return (rate.price_usd * usdToCny.value * row.weight).toFixed(2)
}

async function fetchShippingConfig() {
  try {
    const [tplRes, rateRes] = await Promise.all([
      api.get('/api/shipping/default-template'),
      api.get('/api/shops/exchange-rates'),
    ])
    const tplId = tplRes.data.id
    if (tplId) {
      const { data } = await api.get('/api/shipping/templates')
      const tpl = data.find(t => t.id === tplId)
      if (tpl) shippingRates.value = tpl.rates
    }
    const cnyUsd = rateRes.data.cny_usd || 0
    usdToCny.value = cnyUsd ? parseFloat((1 / cnyUsd).toFixed(2)) : 0
  } catch { /* ignore */ }
}

async function savePackingQty(row) {
  try {
    await api.put(`/api/products/${row.id}`, { packing_qty: row.packing_qty || 0 })
  } catch {
    ElMessage.error('保存失败')
  }
}

async function saveActualShipping(row) {
  try {
    await api.put(`/api/products/${row.id}`, { actual_shipping_cost: row.actual_shipping_cost || 0 })
  } catch {
    ElMessage.error('保存失败')
  }
}

const showDialog = ref(false)
const defaultForm = { id: null, developer: '', sku: '', name: '', purchase_price: 0, weight: 0, length: 0, width: 0, height: 0, packing_qty: 0, actual_shipping_cost: 0 }
const form = reactive({ ...defaultForm })
const pendingImage = ref(null)
const imagePreview = ref('')
const imgUploaderRef = ref(null)
const imageRemoved = ref(false)

async function fetchUserNames() {
  try {
    const { data } = await api.get('/api/users/names')
    userNames.value = data.map(u => u.display_name || u.username).filter(Boolean)
  } catch { /* ignore */ }
}

async function fetchProducts() {
  try {
    const { data } = await api.get('/api/products')
    products.value = data
  } catch (e) {
    console.error('Fetch products error:', e)
    ElMessage.error('数据加载失败')
  }
}

function openDialog(row) {
  if (row) {
    Object.assign(form, row)
    imagePreview.value = row.image ? imageUrl(row.image) : ''
  } else {
    Object.assign(form, defaultForm)
    imagePreview.value = ''
  }
  pendingImage.value = null
  imageRemoved.value = false
  showDialog.value = true
}

function onImageFile(file) {
  pendingImage.value = file
  imageRemoved.value = false
}

function onImageRemove() {
  pendingImage.value = null
  imageRemoved.value = true
}

async function uploadImage(productId) {
  if (!pendingImage.value) return
  const formData = new FormData()
  formData.append('file', pendingImage.value)
  await api.post(`/api/products/${productId}/image`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

async function saveProduct() {
  try {
    const payload = { developer: form.developer, sku: form.sku, name: form.name, purchase_price: form.purchase_price, weight: form.weight, length: form.length, width: form.width, height: form.height, packing_qty: form.packing_qty, actual_shipping_cost: form.actual_shipping_cost }
    let productId = form.id
    if (form.id) {
      await api.put(`/api/products/${form.id}`, payload)
    } else {
      const { data } = await api.post('/api/products', payload)
      productId = data.id
    }
    if (pendingImage.value && productId) {
      await uploadImage(productId)
    } else if (imageRemoved.value && productId) {
      await api.put(`/api/products/${productId}`, { image: '' })
    }
    showDialog.value = false
    fetchProducts()
    ElMessage.success('保存成功')
  } catch (e) {
    console.error('Save product error:', e)
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function deleteProduct(id) {
  try {
    await api.delete(`/api/products/${id}`)
    fetchProducts()
    ElMessage.success('删除成功')
  } catch (e) {
    console.error('Delete product error:', e)
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(() => {
  fetchProducts()
  fetchUserNames()
  fetchShippingConfig()
})
</script>

<style scoped>
:deep(.el-table .el-table__cell) {
  padding: 2px 0;
}
:deep(.el-table .el-table__row) {
  height: 30px;
}
:deep(.el-input-number .el-input__inner) {
  font-size: 12px;
}
:deep(.el-table .cell) {
  overflow: visible;
  text-overflow: clip;
}
</style>

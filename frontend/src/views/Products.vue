<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center">
        <span>商品管理</span>
        <el-button type="primary" @click="openDialog()">添加商品</el-button>
      </div>
    </template>
    <el-table :data="products" stripe>
      <el-table-column label="图片" width="80" align="center">
        <template #default="{ row }">
          <el-image v-if="row.image" :src="row.image" style="width: 50px; height: 50px; display: block; cursor: pointer" fit="contain" :preview-src-list="[row.image]" preview-teleported />
          <span v-else style="color: #ccc">无图</span>
        </template>
      </el-table-column>
      <el-table-column prop="sku" label="商品SKU" min-width="130" />
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column prop="purchase_price" label="采购价" align="center" min-width="90">
        <template #default="{ row }">¥ {{ row.purchase_price }}</template>
      </el-table-column>
      <el-table-column prop="weight" label="重量(g)" align="center" min-width="80" />
      <el-table-column prop="length" label="长(cm)" align="center" min-width="70" />
      <el-table-column prop="width" label="宽(cm)" align="center" min-width="70" />
      <el-table-column prop="height" label="高(cm)" align="center" min-width="70" />
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
      <el-form-item label="商品SKU"><el-input v-model="form.sku" /></el-form-item>
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="采购价"><el-input-number v-model="form.purchase_price" :min="0" :precision="2" /></el-form-item>
      <el-form-item label="重量(g)"><el-input-number v-model="form.weight" :min="0" /></el-form-item>
      <el-form-item label="长(cm)"><el-input-number v-model="form.length" :min="0" /></el-form-item>
      <el-form-item label="宽(cm)"><el-input-number v-model="form.width" :min="0" /></el-form-item>
      <el-form-item label="高(cm)"><el-input-number v-model="form.height" :min="0" /></el-form-item>
      <el-form-item label="商品图片">
        <el-upload
          drag
          :auto-upload="false"
          :show-file-list="false"
          accept="image/*"
          :on-change="onImageChange"
          style="width: 100%"
        >
          <div style="display: flex; align-items: center; gap: 12px; padding: 8px 16px">
            <el-image v-if="imagePreview" :src="imagePreview" style="width: 50px; height: 50px; flex-shrink: 0; border-radius: 4px" fit="cover" />
            <el-icon v-else style="font-size: 24px; color: #c0c4cc; flex-shrink: 0"><UploadFilled /></el-icon>
            <span style="color: #999; font-size: 13px">{{ imagePreview ? '点击或拖拽替换图片' : '拖拽或点击上传图片' }}</span>
          </div>
        </el-upload>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showDialog = false">取消</el-button>
      <el-button type="primary" @click="saveProduct">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import api from '../api'

const products = ref([])
const showDialog = ref(false)
const defaultForm = { id: null, sku: '', name: '', purchase_price: 0, weight: 0, length: 0, width: 0, height: 0 }
const form = reactive({ ...defaultForm })
const pendingImage = ref(null)
const imagePreview = ref('')

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
    imagePreview.value = row.image || ''
  } else {
    Object.assign(form, defaultForm)
    imagePreview.value = ''
  }
  pendingImage.value = null
  showDialog.value = true
}

function onImageChange(file) {
  pendingImage.value = file.raw
  if (imagePreview.value && imagePreview.value.startsWith('blob:')) {
    URL.revokeObjectURL(imagePreview.value)
  }
  imagePreview.value = URL.createObjectURL(file.raw)
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
    const payload = { sku: form.sku, name: form.name, purchase_price: form.purchase_price, weight: form.weight, length: form.length, width: form.width, height: form.height }
    let productId = form.id
    if (form.id) {
      await api.put(`/api/products/${form.id}`, payload)
    } else {
      const { data } = await api.post('/api/products', payload)
      productId = data.id
    }
    if (pendingImage.value && productId) {
      await uploadImage(productId)
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

onMounted(fetchProducts)
</script>

<style scoped>
:deep(.el-table .el-table__cell) {
  padding: 2px 0;
}
:deep(.el-table .el-table__row) {
  height: 30px;
}
</style>

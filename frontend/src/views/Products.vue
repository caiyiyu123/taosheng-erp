<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center">
        <span>商品管理</span>
        <el-button type="primary" @click="openDialog()">添加商品</el-button>
      </div>
    </template>
    <el-table :data="products" stripe>
      <el-table-column label="图片" width="80">
        <template #default="{ row }">
          <el-image v-if="row.image" :src="row.image" style="width: 50px; height: 50px" fit="cover" />
          <span v-else style="color: #ccc">无图</span>
        </template>
      </el-table-column>
      <el-table-column prop="sku" label="商品SKU" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="purchase_price" label="采购价">
        <template #default="{ row }">¥ {{ row.purchase_price }}</template>
      </el-table-column>
      <el-table-column prop="weight" label="重量(g)" />
      <el-table-column label="尺寸(cm)">
        <template #default="{ row }">{{ row.length }} × {{ row.width }} × {{ row.height }}</template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="openDialog(row)">编辑</el-button>
          <el-upload :action="`/api/products/${row.id}/image`" :headers="{ Authorization: `Bearer ${token}` }" :show-file-list="false" @success="fetchProducts" style="display: inline-block; margin: 0 8px">
            <el-button size="small">上传图片</el-button>
          </el-upload>
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
import api from '../api'

const products = ref([])
const showDialog = ref(false)
const token = localStorage.getItem('token')
const defaultForm = { id: null, sku: '', name: '', purchase_price: 0, weight: 0, length: 0, width: 0, height: 0 }
const form = reactive({ ...defaultForm })

async function fetchProducts() {
  const { data } = await api.get('/api/products')
  products.value = data
}

function openDialog(row) {
  if (row) {
    Object.assign(form, row)
  } else {
    Object.assign(form, defaultForm)
  }
  showDialog.value = true
}

async function saveProduct() {
  if (form.id) {
    await api.put(`/api/products/${form.id}`, form)
  } else {
    await api.post('/api/products', form)
  }
  showDialog.value = false
  fetchProducts()
  ElMessage.success('保存成功')
}

async function deleteProduct(id) {
  await api.delete(`/api/products/${id}`)
  fetchProducts()
  ElMessage.success('删除成功')
}

onMounted(fetchProducts)
</script>

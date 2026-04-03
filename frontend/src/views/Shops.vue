<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center">
        <span>店铺管理</span>
        <el-button v-if="isAdmin" type="primary" @click="openDialog()">添加店铺</el-button>
      </div>
    </template>
    <el-table :data="shops" stripe>
      <el-table-column prop="name" label="店铺名称" />
      <el-table-column prop="type" label="类型">
        <template #default="{ row }">
          <el-tag :type="row.type === 'local' ? 'success' : 'warning'">{{ row.type === 'local' ? '本土' : '跨境' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最后同步">
        <template #default="{ row }">{{ formatTime(row.last_sync_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="320">
        <template #default="{ row }">
          <el-button size="small" @click="openDialog(row)">编辑</el-button>
          <el-button size="small" type="success" @click="$router.push(`/shops/${row.id}/sku-mappings`)">SKU关联</el-button>
          <el-button size="small" type="warning" :loading="syncing === row.id" @click="syncShop(row.id)">同步</el-button>
          <el-popconfirm v-if="isAdmin" title="确定删除该店铺？此操作不可恢复！" confirm-button-text="确认删除" cancel-button-text="取消" confirm-button-type="danger" @confirm="deleteShop(row.id)">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="showDialog" :title="form.id ? '编辑店铺' : '添加店铺'" width="500px">
    <el-form :model="form" label-width="100px">
      <el-form-item label="店铺名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="类型">
        <el-select v-model="form.type">
          <el-option label="本土" value="local" />
          <el-option label="跨境" value="cross_border" />
        </el-select>
      </el-form-item>
      <el-form-item label="API Token"><el-input v-model="form.api_token" type="password" show-password /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showDialog = false">取消</el-button>
      <el-button type="primary" @click="saveShop">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const shops = ref([])
const showDialog = ref(false)
const syncing = ref(null)
const defaultForm = { id: null, name: '', type: 'local', api_token: '' }
const form = reactive({ ...defaultForm })

function formatTime(dt) {
  if (!dt) return '-'
  const utcDt = String(dt).endsWith('Z') ? dt : dt + 'Z'
  return new Date(utcDt).toLocaleString('zh-CN', { timeZone: 'Europe/Moscow' })
}

async function fetchShops() {
  const { data } = await api.get('/api/shops')
  shops.value = data
}

function openDialog(row) {
  if (row) {
    Object.assign(form, { ...row, api_token: '' })
  } else {
    Object.assign(form, defaultForm)
  }
  showDialog.value = true
}

async function saveShop() {
  try {
    if (form.id) {
      const payload = { name: form.name, type: form.type }
      if (form.api_token) payload.api_token = form.api_token
      await api.put(`/api/shops/${form.id}`, payload)
    } else {
      const { name, type, api_token } = form
      await api.post('/api/shops', { name, type, api_token })
    }
    showDialog.value = false
    fetchShops()
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function deleteShop(id) {
  await api.delete(`/api/shops/${id}`)
  fetchShops()
  ElMessage.success('删除成功')
}

async function syncShop(id) {
  if (syncing.value === id) return
  syncing.value = id
  try {
    await api.post(`/api/shops/${id}/sync`)
    // Poll for completion
    const poll = setInterval(async () => {
      try {
        const { data } = await api.get(`/api/shops/${id}/sync-status`)
        if (data.status === 'done') {
          clearInterval(poll)
          syncing.value = null
          ElMessage.success('同步完成')
          fetchShops()
        } else if (data.status === 'error') {
          clearInterval(poll)
          syncing.value = null
          ElMessage.error(`同步失败: ${data.detail}`)
        }
      } catch {
        clearInterval(poll)
        syncing.value = null
      }
    }, 3000)
  } catch {
    ElMessage.error('同步请求失败')
    syncing.value = null
  }
}

onMounted(fetchShops)
</script>

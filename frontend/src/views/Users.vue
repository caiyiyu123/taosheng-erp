<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center">
        <span>用户管理</span>
        <el-button type="primary" @click="openDialog()">添加用户</el-button>
      </div>
    </template>
    <el-table :data="users" stripe>
      <el-table-column prop="username" label="用户名" min-width="100" />
      <el-table-column prop="display_name" label="姓名" min-width="100" />
      <el-table-column prop="role" label="角色" width="90">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : 'warning'">{{ roleLabel(row.role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="可访问店铺" min-width="160">
        <template #default="{ row }">
          <template v-if="row.role === 'admin'">
            <el-tag type="danger" size="small">全部店铺</el-tag>
          </template>
          <template v-else>
            <el-tag v-for="sid in row.shop_ids" :key="sid" size="small" style="margin-right: 4px">
              {{ shopName(sid) }}
            </el-tag>
            <span v-if="!row.shop_ids?.length" style="color: var(--ts-text-muted)">未分配</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="模块权限" min-width="240">
        <template #default="{ row }">
          <template v-if="row.role === 'admin'">
            <el-tag type="danger" size="small">全部模块</el-tag>
          </template>
          <template v-else>
            <el-tag v-for="m in row.permissions" :key="m" size="small" style="margin-right: 4px">
              {{ moduleLabel(m) }}
            </el-tag>
            <span v-if="!row.permissions?.length" style="color: var(--ts-text-muted)">无权限</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确定删除?" @confirm="deleteUser(row.id)">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="showDialog" :title="form.id ? '编辑用户' : '添加用户'" width="560px">
    <el-form :model="form" label-width="100px">
      <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="姓名"><el-input v-model="form.display_name" placeholder="真实姓名" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="form.password" type="password" :placeholder="form.id ? '留空不修改' : ''" /></el-form-item>
      <el-form-item label="角色">
        <el-select v-model="form.role" @change="onRoleChange">
          <el-option label="管理员" value="admin" />
          <el-option label="运营" value="operator" />
        </el-select>
      </el-form-item>
      <el-form-item label="可访问店铺" v-if="form.role !== 'admin'">
        <el-select v-model="form.shop_ids" multiple placeholder="选择店铺" style="width: 100%">
          <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <div style="color: #999; font-size: 12px; margin-top: 4px">不选择则无法查看任何店铺数据</div>
      </el-form-item>
      <el-form-item label="模块权限" v-if="form.role !== 'admin'">
        <el-checkbox-group v-model="form.permissions">
          <el-checkbox v-for="m in allModules" :key="m.value" :value="m.value" :label="m.value">
            {{ m.label }}
          </el-checkbox>
        </el-checkbox-group>
        <div style="margin-top: 8px">
          <el-button size="small" link type="primary" @click="form.permissions = allModules.map(m => m.value)">全选</el-button>
          <el-button size="small" link @click="form.permissions = []">全不选</el-button>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showDialog = false">取消</el-button>
      <el-button type="primary" @click="saveUser">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const users = ref([])
const shops = ref([])
const showDialog = ref(false)
const defaultForm = { id: null, username: '', display_name: '', password: '', role: 'operator', shop_ids: [], permissions: [] }
const form = reactive({ ...defaultForm })

const ROLE_MAP = { admin: '管理员', operator: '运营' }
function roleLabel(role) { return ROLE_MAP[role] || role }
function shopName(id) {
  const s = shops.value.find(s => s.id === id)
  return s ? s.name : `#${id}`
}

const allModules = [
  { value: 'dashboard', label: '仪表盘' },
  { value: 'orders', label: '订单管理' },
  { value: 'products', label: '商品管理' },
  { value: 'ads', label: '推广数据' },
  { value: 'finance', label: '财务管理' },
  { value: 'customer_service', label: '评价客服' },
  { value: 'commission_shipping', label: '佣金运费' },
  { value: 'inventory', label: '库存管理' },
  { value: 'shops', label: '店铺管理' },
]

const MODULE_MAP = Object.fromEntries(allModules.map(m => [m.value, m.label]))
function moduleLabel(m) { return MODULE_MAP[m] || m }

function onRoleChange(val) {
  if (val === 'admin') {
    form.shop_ids = []
    form.permissions = []
  }
}

async function fetchUsers() {
  try {
    const { data } = await api.get('/api/users')
    users.value = data
  } catch (e) {
    console.error('Fetch users error:', e)
    ElMessage.error('数据加载失败')
  }
}

function openDialog(row) {
  if (row) {
    Object.assign(form, { ...row, password: '', shop_ids: row.shop_ids || [], permissions: row.permissions || [] })
  } else {
    Object.assign(form, { ...defaultForm, shop_ids: [], permissions: [] })
  }
  showDialog.value = true
}

async function saveUser() {
  try {
    const isAdmin = form.role === 'admin'
    if (form.id) {
      const payload = {
        role: form.role,
        shop_ids: isAdmin ? [] : form.shop_ids,
        permissions: isAdmin ? [] : form.permissions,
      }
      if (form.username) payload.username = form.username
      payload.display_name = form.display_name || ''
      if (form.password) payload.password = form.password
      await api.put(`/api/users/${form.id}`, payload)
    } else {
      await api.post('/api/users', {
        ...form,
        shop_ids: isAdmin ? [] : form.shop_ids,
        permissions: isAdmin ? [] : form.permissions,
      })
    }
    showDialog.value = false
    Object.assign(form, { ...defaultForm, shop_ids: [], permissions: [] })
    fetchUsers()
    ElMessage.success('保存成功')
  } catch (e) {
    console.error('Save user error:', e)
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function deleteUser(id) {
  try {
    await api.delete(`/api/users/${id}`)
    fetchUsers()
    ElMessage.success('删除成功')
  } catch (e) {
    console.error('Delete user error:', e)
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(async () => {
  try {
    const [, shopRes] = await Promise.all([fetchUsers(), api.get('/api/shops')])
    shops.value = shopRes.data
  } catch (e) {
    console.error('Init users page error:', e)
  }
})
</script>

<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center">
        <div style="display: flex; align-items: center; gap: 12px">
          <span>采购计划</span>
          <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width: 130px" @change="fetchPlans">
            <el-option label="待采购" value="pending" />
            <el-option label="已采购" value="purchased" />
            <el-option label="已到货" value="arrived" />
          </el-select>
        </div>
        <el-button type="primary" @click="openDialog()">新增采购计划</el-button>
      </div>
    </template>
    <el-table :data="flatRows" stripe v-loading="loading" :span-method="spanMethod">
      <el-table-column prop="operator_name" label="采购员" width="100" />
      <el-table-column prop="purchase_date" label="采购日期" width="120" />
      <el-table-column label="商品图片" width="80" align="center">
        <template #default="{ row }">
          <el-image v-if="row.product_image" :src="imageUrl(row.product_image)" style="width: 40px; height: 40px" fit="contain" />
          <span v-else style="color: #ccc">无图</span>
        </template>
      </el-table-column>
      <el-table-column prop="product_sku" label="商品SKU" min-width="120" />
      <el-table-column prop="product_name" label="商品名称" min-width="120" />
      <el-table-column label="数量" width="80" align="center">
        <template #default="{ row }"><span style="font-weight: 600">{{ row.quantity }}</span></template>
      </el-table-column>
      <el-table-column prop="boxes" label="箱数" width="80" align="center" />
      <el-table-column label="采购单价" width="100" align="center">
        <template #default="{ row }">¥ {{ row.unit_price?.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="快递费用" width="100" align="center">
        <template #default="{ row }">¥ {{ row.express_fee?.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="采购总金额" width="110" align="center">
        <template #default="{ row }">
          <span style="font-weight: 600; color: #e6a23c">¥ {{ row._total }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="150" align="center">
        <template #default="{ row }">
          <el-dropdown trigger="click" @command="cmd => changeStatus(row._planId, cmd)">
            <el-tag :type="statusType(row.status)" size="large" style="cursor: pointer; font-size: 15px; padding: 4px 20px; line-height: 24px">{{ statusLabel(row.status) }} ▾</el-tag>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="pending" :disabled="row.status === 'pending'">
                  <el-tag type="warning" size="large" style="font-size: 15px; padding: 4px 20px">待采购</el-tag>
                </el-dropdown-item>
                <el-dropdown-item command="purchased" :disabled="row.status === 'purchased'">
                  <el-tag type="primary" size="large" style="font-size: 15px; padding: 4px 20px">已采购</el-tag>
                </el-dropdown-item>
                <el-dropdown-item command="arrived" :disabled="row.status === 'arrived'">
                  <el-tag type="success" size="large" style="font-size: 15px; padding: 4px 20px">已到货</el-tag>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center">
        <template #default="{ row }">
          <el-button size="small" link @click="openDialog(row._plan)">编辑</el-button>
          <el-button size="small" link type="primary" @click="copyPlan(row._plan)">复制</el-button>
          <el-popconfirm title="确定删除该采购计划?" @confirm="deletePlan(row._planId)">
            <template #reference>
              <el-button size="small" link type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <!-- 展开行：显示商品明细 -->

  <!-- 新增/编辑对话框 -->
  <el-dialog v-model="showDialog" :title="form.id ? '编辑采购计划' : '新增采购计划'" width="900px" top="5vh">
    <el-form :model="form" label-width="90px">
      <div style="display: flex; gap: 16px">
        <el-form-item label="采购员" style="flex: 1">
          <el-select v-model="form.operator_name" placeholder="选择运营" style="width: 100%">
            <el-option v-for="u in userNames" :key="u" :label="u" :value="u" />
          </el-select>
        </el-form-item>
        <el-form-item label="采购日期" style="flex: 1">
          <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
      </div>
      <el-form-item label="添加商品">
        <el-select
          v-model="selectedProduct"
          filterable
          placeholder="输入SKU或商品名称搜索"
          style="width: 100%"
          @change="onProductSelected"
        >
          <el-option
            v-for="p in allProducts"
            :key="p.id"
            :label="`${p.sku} - ${p.name}`"
            :value="p.id"
          />
        </el-select>
      </el-form-item>
      <el-table :data="form.items" style="margin-bottom: 16px">
        <el-table-column label="图片" width="70" align="center">
          <template #default="{ row }">
            <el-image v-if="row.product_image" :src="imageUrl(row.product_image)" style="width: 40px; height: 40px" fit="contain" />
            <span v-else style="color: #ccc">无图</span>
          </template>
        </el-table-column>
        <el-table-column prop="product_sku" label="商品SKU" min-width="120" />
        <el-table-column prop="product_name" label="商品名称" min-width="120" />
        <el-table-column label="采购单价" width="130" align="center">
          <template #default="{ row }">
            <el-input-number v-model="row.unit_price" :min="0" :precision="2" :controls="false" size="small" style="width: 100px" />
          </template>
        </el-table-column>
        <el-table-column label="数量" width="110" align="center">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0" :precision="0" :controls="false" size="small" style="width: 80px" />
          </template>
        </el-table-column>
        <el-table-column label="装箱数" width="110" align="center">
          <template #default="{ row }">
            <el-input-number v-model="row.boxes" :min="0" :precision="0" :controls="false" size="small" style="width: 80px" />
          </template>
        </el-table-column>
        <el-table-column label="箱数" width="80" align="center">
          <template #default="{ row }">
            <span>{{ row.boxes ? Math.ceil(row.quantity / row.boxes) : 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="小计" width="120" align="right">
          <template #default="{ row }">
            <span style="font-weight: 600; white-space: nowrap">¥ {{ (row.quantity * row.unit_price).toFixed(1) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" align="center">
          <template #default="{ $index }">
            <el-button :icon="Delete" circle size="small" @click="form.items.splice($index, 1)" />
          </template>
        </el-table-column>
      </el-table>
      <div style="display: flex; justify-content: flex-end; align-items: center; gap: 24px">
        <el-form-item label="快递费用" style="margin-bottom: 0">
          <el-input-number v-model="form.express_fee" :min="0" :precision="2" style="width: 140px" />
        </el-form-item>
        <div style="font-size: 15px; font-weight: 600">
          采购总金额：<span style="color: #e6a23c">¥ {{ calcFormTotal }}</span>
        </div>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="showDialog = false">取消</el-button>
      <el-button type="primary" @click="savePlan">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import api, { imageUrl } from '../api'

const plans = ref([])
const loading = ref(false)
const filterStatus = ref('')
const showDialog = ref(false)
const userNames = ref([])
const allProducts = ref([])
const selectedProduct = ref(null)

const form = reactive({
  id: null,
  operator_name: '',
  purchase_date: '',
  express_fee: 0,
  items: [],
})

const STATUS_MAP = { pending: '待采购', purchased: '已采购', arrived: '已到货' }
const STATUS_TYPE = { pending: 'warning', purchased: 'primary', arrived: 'success' }
function statusLabel(s) { return STATUS_MAP[s] || s }
function statusType(s) { return STATUS_TYPE[s] || 'info' }

function calcTotal(plan) {
  const itemsTotal = plan.items.reduce((sum, i) => sum + i.quantity * i.unit_price, 0)
  return (itemsTotal + (plan.express_fee || 0)).toFixed(1)
}

// 合并列索引：采购员(0), 采购日期(1), 快递费用(8), 采购总金额(9), 状态(10), 操作(11)
const MERGE_COLS = new Set([0, 1, 8, 9, 10, 11])

const flatRows = computed(() => {
  const rows = []
  for (const plan of plans.value) {
    const total = calcTotal(plan)
    const items = plan.items.length ? plan.items : [{}]
    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      rows.push({
        _planId: plan.id,
        _plan: plan,
        _spanCount: i === 0 ? items.length : 0,
        _total: total,
        operator_name: plan.operator_name,
        purchase_date: plan.purchase_date,
        express_fee: plan.express_fee,
        status: plan.status,
        product_image: item.product_image || '',
        product_sku: item.product_sku || '',
        product_name: item.product_name || '',
        quantity: item.quantity || 0,
        boxes: item.boxes || 0,
        unit_price: item.unit_price || 0,
      })
    }
  }
  return rows
})

function spanMethod({ row, columnIndex }) {
  if (MERGE_COLS.has(columnIndex)) {
    if (row._spanCount > 0) return { rowspan: row._spanCount, colspan: 1 }
    return { rowspan: 0, colspan: 0 }
  }
}

const calcFormTotal = computed(() => {
  const itemsTotal = form.items.reduce((sum, i) => sum + (i.quantity || 0) * (i.unit_price || 0), 0)
  return (itemsTotal + (form.express_fee || 0)).toFixed(1)
})

async function fetchPlans() {
  loading.value = true
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await api.get('/api/purchase-plans', { params })
    plans.value = data
  } catch { /* ignore */ }
  finally { loading.value = false }
}

async function fetchUserNames() {
  try {
    const { data } = await api.get('/api/users')
    userNames.value = data.map(u => u.display_name || u.username).filter(Boolean)
  } catch { /* ignore */ }
}

async function fetchProducts() {
  try {
    const { data } = await api.get('/api/products')
    allProducts.value = data
  } catch { /* ignore */ }
}

function onProductSelected(productId) {
  const p = allProducts.value.find(x => x.id === productId)
  if (!p) return
  // 防止重复添加
  if (form.items.some(i => i.product_id === p.id)) {
    ElMessage.warning('该商品已在列表中')
    selectedProduct.value = null
    return
  }
  form.items.push({
    product_id: p.id,
    product_sku: p.sku,
    product_name: p.name,
    product_image: p.image,
    unit_price: p.purchase_price || 0,
    quantity: 0,
    boxes: p.packing_qty || 0,
  })
  selectedProduct.value = null
}

function copyPlan(plan) {
  form.id = null
  form.operator_name = plan.operator_name
  form.purchase_date = ''
  form.express_fee = plan.express_fee
  form.items = plan.items.map(i => ({ ...i }))
  showDialog.value = true
}

function openDialog(row) {
  if (row) {
    form.id = row.id
    form.operator_name = row.operator_name
    form.purchase_date = row.purchase_date
    form.express_fee = row.express_fee
    form.items = row.items.map(i => ({ ...i }))
  } else {
    form.id = null
    form.operator_name = ''
    form.purchase_date = ''
    form.express_fee = 0
    form.items = []
  }
  showDialog.value = true
}

async function savePlan() {
  if (!form.operator_name || !form.purchase_date) {
    ElMessage.warning('请填写采购员和采购日期')
    return
  }
  if (!form.items.length) {
    ElMessage.warning('请至少添加一个商品')
    return
  }
  const payload = {
    operator_name: form.operator_name,
    purchase_date: form.purchase_date,
    express_fee: form.express_fee,
    items: form.items.map(i => ({
      product_id: i.product_id,
      quantity: i.quantity || 0,
      boxes: i.boxes || 0,
      unit_price: i.unit_price || 0,
    })),
  }
  try {
    if (form.id) {
      await api.put(`/api/purchase-plans/${form.id}`, payload)
    } else {
      await api.post('/api/purchase-plans', payload)
    }
    showDialog.value = false
    fetchPlans()
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function deletePlan(id) {
  try {
    await api.delete(`/api/purchase-plans/${id}`)
    fetchPlans()
    ElMessage.success('删除成功')
  } catch {
    ElMessage.error('删除失败')
  }
}

async function changeStatus(id, status) {
  try {
    await api.put(`/api/purchase-plans/${id}/status`, { status })
    fetchPlans()
    ElMessage.success('状态已更新')
  } catch {
    ElMessage.error('状态更新失败')
  }
}

onMounted(() => {
  fetchPlans()
  fetchUserNames()
  fetchProducts()
})
</script>

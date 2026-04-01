<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" style="background: #16213e">
      <div style="padding: 16px; color: white; font-size: 1.2em; font-weight: bold; text-align: center; border-bottom: 1px solid #2a3a5e;">
        韬盛ERP
      </div>
      <el-menu
        :default-active="$route.path"
        background-color="#16213e"
        text-color="#ccc"
        active-text-color="#4fc3f7"
        router
      >
        <el-menu-item index="/">
          <el-icon><DataAnalysis /></el-icon>
          <span>数据看板</span>
        </el-menu-item>
        <el-sub-menu index="orders-sub">
          <template #title>
            <el-icon><Box /></el-icon>
            <span>订单管理</span>
          </template>
          <el-menu-item index="/orders?order_type=FBS">FBS 订单</el-menu-item>
          <el-menu-item index="/orders?order_type=FBW">FBW 订单</el-menu-item>
          <el-menu-item index="/orders">全部订单</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="products-sub">
          <template #title>
            <el-icon><Goods /></el-icon>
            <span>商品管理</span>
          </template>
          <el-menu-item index="/products">商品列表</el-menu-item>
          <el-menu-item index="/ads">推广数据</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/finance">
          <el-icon><Money /></el-icon>
          <span>财务统计</span>
        </el-menu-item>
        <el-menu-item index="/inventory">
          <el-icon><List /></el-icon>
          <span>库存管理</span>
        </el-menu-item>
        <el-menu-item index="/shops">
          <el-icon><Shop /></el-icon>
          <span>店铺管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.user?.role === 'admin'" index="/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="background: #1a1a2e; color: white; display: flex; align-items: center; justify-content: flex-end; gap: 16px">
        <span>{{ authStore.user?.username }}</span>
        <el-tag>{{ authStore.user?.role }}</el-tag>
        <el-button text style="color: #ccc" @click="handleLogout">退出</el-button>
      </el-header>
      <el-main style="background: #f0f2f5">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { DataAnalysis, Box, Goods, Money, List, Shop, User } from '@element-plus/icons-vue'

const authStore = useAuthStore()
const router = useRouter()

onMounted(() => {
  if (authStore.token) authStore.fetchUser()
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

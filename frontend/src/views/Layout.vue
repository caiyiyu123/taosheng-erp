<template>
  <el-container class="ts-layout">
    <el-aside width="220px" class="ts-sidebar">
      <div class="ts-logo">
        <img :src="appLogo" alt="Logo" class="ts-logo-icon" />
        <span class="ts-logo-text">{{ appTitle }}</span>
      </div>
      <el-menu
        :default-active="$route.path"
        background-color="transparent"
        text-color="#94a3b8"
        active-text-color="#fbbf24"
      >
        <el-menu-item v-if="hasPerm('dashboard')" index="/">
          <router-link to="/" class="ts-nav-link">
            <el-icon><DataAnalysis /></el-icon>
            <span>数据看板</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('orders')" index="/orders">
          <router-link to="/orders" class="ts-nav-link">
            <el-icon><Box /></el-icon>
            <span>订单管理</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('products')" index="/shop-products">
          <router-link to="/shop-products" class="ts-nav-link">
            <el-icon><ShoppingCart /></el-icon>
            <span>产品管理</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('products')" index="/products">
          <router-link to="/products" class="ts-nav-link">
            <el-icon><Goods /></el-icon>
            <span>商品管理</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('purchase_plan')" index="/purchase-plan">
          <router-link to="/purchase-plan" class="ts-nav-link">
            <el-icon><DocumentChecked /></el-icon>
            <span>采购计划</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('ads')" index="/ads">
          <router-link to="/ads" class="ts-nav-link">
            <el-icon><TrendCharts /></el-icon>
            <span>推广数据</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('finance')" index="/finance">
          <router-link to="/finance" class="ts-nav-link">
            <el-icon><Money /></el-icon>
            <span>财务统计</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('customer_service')" index="/customer-service">
          <router-link to="/customer-service" class="ts-nav-link">
            <el-icon><ChatDotRound /></el-icon>
            <span>评价客服</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('commission_shipping')" index="/commission-shipping">
          <router-link to="/commission-shipping" class="ts-nav-link">
            <el-icon><PriceTag /></el-icon>
            <span>佣金运费</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('inventory')" index="/inventory">
          <router-link to="/inventory" class="ts-nav-link">
            <el-icon><List /></el-icon>
            <span>库存管理</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="hasPerm('shops')" index="/shops">
          <router-link to="/shops" class="ts-nav-link">
            <el-icon><Shop /></el-icon>
            <span>店铺管理</span>
          </router-link>
        </el-menu-item>
        <el-menu-item v-if="isAdmin" index="/users">
          <router-link to="/users" class="ts-nav-link">
            <el-icon><User /></el-icon>
            <span>用户管理</span>
          </router-link>
        </el-menu-item>
      </el-menu>
      <div class="ts-sidebar-footer">
        <div class="ts-sidebar-divider"></div>
        <div class="ts-version">v1.0</div>
      </div>
    </el-aside>
    <el-container>
      <el-header class="ts-header">
        <div class="ts-header-left"></div>
        <div class="ts-header-right">
          <span class="ts-username">{{ authStore.user?.username }}</span>
          <el-tag :type="isAdmin ? 'danger' : 'warning'" size="small" effect="dark" round>
            {{ isAdmin ? '管理员' : '运营' }}
          </el-tag>
          <button class="ts-logout-btn" @click="handleLogout">退出</button>
        </div>
      </el-header>
      <el-main class="ts-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { DataAnalysis, Box, ShoppingCart, Goods, TrendCharts, Money, List, Shop, User, ChatDotRound, PriceTag, DocumentChecked } from '@element-plus/icons-vue'
import { APP_TITLE, APP_LOGO } from '../brand'

const appTitle = APP_TITLE
const appLogo = APP_LOGO

const authStore = useAuthStore()
const router = useRouter()

const isAdmin = computed(() => authStore.user?.role === 'admin')

function hasPerm(module) {
  if (!authStore.user) return false
  if (authStore.user.role === 'admin') return true
  return authStore.user.permissions?.includes(module)
}

onMounted(() => {
  if (authStore.token) authStore.fetchUser()
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.ts-layout {
  height: 100vh;
  background: var(--ts-bg-deep);
}

/* ---- Sidebar (stays dark) ---- */
.ts-sidebar {
  background: var(--ts-bg-dark);
  border-right: none;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  box-shadow: 2px 0 12px rgba(0, 0, 0, 0.15);
}
.ts-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 20px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  margin-bottom: 8px;
}
.ts-logo-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
  background: #ffffff;
}
.ts-logo-text {
  font-size: 18px;
  font-weight: 700;
  color: #f8fafc;
  letter-spacing: 1px;
}
.ts-sidebar-footer {
  margin-top: auto;
  padding: 12px 20px 16px;
}
.ts-sidebar-divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.06);
  margin-bottom: 12px;
}
.ts-version {
  font-size: 11px;
  color: #64748b;
  text-align: center;
  letter-spacing: 1px;
}

/* ---- Header (light) ---- */
.ts-header {
  background: #ffffff;
  border-bottom: 1px solid var(--ts-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
}
.ts-header-right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.ts-username {
  font-size: 14px;
  font-weight: 500;
  color: var(--ts-text-primary);
}
.ts-logout-btn {
  background: none;
  border: 1px solid #d1d5db;
  color: var(--ts-text-muted);
  font-family: var(--ts-font);
  font-size: 13px;
  font-weight: 500;
  padding: 4px 14px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.ts-logout-btn:hover {
  color: var(--ts-danger);
  border-color: rgba(220, 38, 38, 0.3);
  background: rgba(220, 38, 38, 0.06);
}

/* ---- Sidebar nav links (enable right-click open in new tab) ---- */
.ts-nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 100%;
  color: inherit;
  text-decoration: none;
}
:deep(.el-menu-item) {
  padding: 0 !important;
}
.ts-nav-link {
  padding: 0 20px;
}

/* ---- Main content (light bg) ---- */
.ts-main {
  background: var(--ts-bg-deep);
  padding: 24px;
  overflow-y: auto;
}
</style>

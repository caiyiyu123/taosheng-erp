import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue') },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', meta: { module: 'dashboard' }, component: () => import('../views/Dashboard.vue') },
      { path: 'orders', name: 'Orders', meta: { module: 'orders' }, component: () => import('../views/Orders.vue') },
      { path: 'orders/:id', name: 'OrderDetail', meta: { module: 'orders' }, component: () => import('../views/OrderDetail.vue') },
      { path: 'shop-products', name: 'ShopProducts', meta: { module: 'products' }, component: () => import('../views/ShopProducts.vue') },
      { path: 'products', name: 'Products', meta: { module: 'products' }, component: () => import('../views/Products.vue') },
      { path: 'ads', name: 'AdsOverview', meta: { module: 'ads' }, component: () => import('../views/AdsOverview.vue') },
      { path: 'ads/:id', name: 'AdDetail', meta: { module: 'ads' }, component: () => import('../views/AdDetail.vue') },
      { path: 'finance', name: 'Finance', meta: { module: 'finance' }, component: () => import('../views/Finance.vue') },
      { path: 'inventory', name: 'Inventory', meta: { module: 'inventory' }, component: () => import('../views/Inventory.vue') },
      { path: 'shops', name: 'Shops', meta: { module: 'shops' }, component: () => import('../views/Shops.vue') },
      { path: 'shops/:id/sku-mappings', name: 'SkuMappings', meta: { module: 'shops' }, component: () => import('../views/SkuMappings.vue') },
      { path: 'users', name: 'Users', meta: { module: 'users', adminOnly: true }, component: () => import('../views/Users.vue') },
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
    return
  }

  // 权限检查
  if (token && to.meta.module) {
    const authStore = useAuthStore()
    // 确保用户信息已加载
    if (!authStore.user) {
      try {
        await authStore.fetchUser()
      } catch (e) {
        next('/login')
        return
      }
    }
    const user = authStore.user
    if (user) {
      // admin 可以访问所有模块
      if (user.role === 'admin') {
        next()
        return
      }
      // adminOnly 路由非 admin 不可访问
      if (to.meta.adminOnly) {
        next('/')
        return
      }
      // 检查模块权限
      const permissions = user.permissions || []
      if (!permissions.includes(to.meta.module)) {
        next('/')
        return
      }
    }
  }

  next()
})

export default router

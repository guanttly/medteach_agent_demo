import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/home', name: 'home', component: () => import('../pages/Home.vue') },
    { path: '/screen', name: 'screen', component: () => import('../pages/BigScreen.vue') },
    { path: '/avatar', name: 'avatar', component: () => import('../pages/Avatar.vue') },
    { path: '/control', name: 'control', component: () => import('../pages/Control.vue') }
  ]
})

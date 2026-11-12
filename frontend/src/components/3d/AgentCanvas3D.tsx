import React, { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'

interface AgentCanvas3DProps {
  className?: string
  interactive?: boolean
}

export const AgentCanvas3D: React.FC<AgentCanvas3DProps> = ({
  className = '',
  interactive = true,
}) => {
  const mountRef = useRef<HTMLDivElement>(null)
  const [hasWebGL, setHasWebGL] = useState<boolean>(true)

  useEffect(() => {
    const container = mountRef.current
    if (!container) return

    // 1. Check WebGL support
    try {
      const canvas = document.createElement('canvas')
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl')
      if (!gl) {
        setHasWebGL(false)
        return
      }
    } catch {
      setHasWebGL(false)
      return
    }

    const width = container.clientWidth || 450
    const height = container.clientHeight || 450

    // 2. Scene, Camera, Renderer
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 100)
    camera.position.set(0, 0.2, 5.2)

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance',
    })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.15
    container.appendChild(renderer.domElement)

    // 3. Lighting (Soft, warm, tactile)
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.4)
    scene.add(ambientLight)

    const keyLight = new THREE.DirectionalLight(0xfff7ed, 1.8)
    keyLight.position.set(3, 4, 4)
    keyLight.castShadow = true
    keyLight.shadow.mapSize.width = 1024
    keyLight.shadow.mapSize.height = 1024
    keyLight.shadow.bias = -0.0001
    scene.add(keyLight)

    const fillLight = new THREE.DirectionalLight(0xdcfce7, 1.2)
    fillLight.position.set(-3, 1, 2)
    scene.add(fillLight)

    const rimLight = new THREE.DirectionalLight(0xa7f3d0, 1.4)
    rimLight.position.set(0, 3, -4)
    scene.add(rimLight)

    // 4. Creature Group
    const creature = new THREE.Group()
    scene.add(creature)

    // A. Main Body (Pill/Bean shape via CapsuleGeometry or deformed sphere)
    const bodyGeo = new THREE.CapsuleGeometry(0.85, 0.95, 32, 64)
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0xc8ecd4, // soft pistachio mint
      roughness: 0.65,
      metalness: 0.05,
      bumpScale: 0.02,
    })
    const bodyMesh = new THREE.Mesh(bodyGeo, bodyMat)
    bodyMesh.castShadow = true
    bodyMesh.receiveShadow = true
    creature.add(bodyMesh)

    // B. Eyes Group (left and right)
    const eyeGroup = new THREE.Group()
    eyeGroup.position.set(0, 0.22, 0.82)
    creature.add(eyeGroup)

    const eyeGeo = new THREE.SphereGeometry(0.065, 32, 32)
    const eyeMat = new THREE.MeshStandardMaterial({
      color: 0x111827,
      roughness: 0.1,
      metalness: 0.9,
    })

    // Specular shine for eyes
    const shineGeo = new THREE.SphereGeometry(0.02, 16, 16)
    const shineMat = new THREE.MeshBasicMaterial({ color: 0xffffff })

    const leftEye = new THREE.Mesh(eyeGeo, eyeMat)
    leftEye.position.set(-0.25, 0, 0)
    const leftShine = new THREE.Mesh(shineGeo, shineMat)
    leftShine.position.set(0.02, 0.025, 0.055)
    leftEye.add(leftShine)
    eyeGroup.add(leftEye)

    const rightEye = new THREE.Mesh(eyeGeo, eyeMat)
    rightEye.position.set(0.25, 0, 0)
    const rightShine = new THREE.Mesh(shineGeo, shineMat)
    rightShine.position.set(0.02, 0.025, 0.055)
    rightEye.add(rightShine)
    eyeGroup.add(rightEye)

    // C. Rosy Cheeks
    const cheekGeo = new THREE.SphereGeometry(0.075, 16, 16)
    cheekGeo.scale(1.2, 0.6, 0.4)
    const cheekMat = new THREE.MeshBasicMaterial({
      color: 0xfca5a5,
      transparent: true,
      opacity: 0.65,
    })
    const leftCheek = new THREE.Mesh(cheekGeo, cheekMat)
    leftCheek.position.set(-0.38, -0.09, 0.78)
    creature.add(leftCheek)

    const rightCheek = new THREE.Mesh(cheekGeo, cheekMat)
    rightCheek.position.set(0.38, -0.09, 0.78)
    creature.add(rightCheek)

    // D. Smile (Subtle Torus curve)
    const smileGeo = new THREE.TorusGeometry(0.05, 0.012, 16, 32, Math.PI)
    const smileMat = new THREE.MeshBasicMaterial({ color: 0x1f2937 })
    const smile = new THREE.Mesh(smileGeo, smileMat)
    smile.position.set(0, -0.05, 0.85)
    smile.rotation.x = Math.PI
    creature.add(smile)

    // E. Tiny Feet
    const footGeo = new THREE.CapsuleGeometry(0.18, 0.22, 16, 16)
    const footMat = new THREE.MeshStandardMaterial({
      color: 0xb5e0c2,
      roughness: 0.7,
    })
    const leftFoot = new THREE.Mesh(footGeo, footMat)
    leftFoot.position.set(-0.35, -1.25, 0)
    leftFoot.rotation.x = Math.PI / 2
    creature.add(leftFoot)

    const rightFoot = new THREE.Mesh(footGeo, footMat)
    rightFoot.position.set(0.35, -1.25, 0)
    rightFoot.rotation.x = Math.PI / 2
    creature.add(rightFoot)

    // F. Ground Soft Shadow Disk
    const shadowGeo = new THREE.CircleGeometry(0.95, 32)
    const shadowMat = new THREE.MeshBasicMaterial({
      color: 0xa7d8b8,
      transparent: true,
      opacity: 0.25,
    })
    const shadowMesh = new THREE.Mesh(shadowGeo, shadowMat)
    shadowMesh.rotation.x = -Math.PI / 2
    shadowMesh.position.y = -1.45
    scene.add(shadowMesh)

    // 5. Mouse / Pointer Tracking
    const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 }

    const onPointerMove = (e: MouseEvent | TouchEvent) => {
      if (!interactive) return
      let clientX = 0
      let clientY = 0

      if ('touches' in e && e.touches.length > 0) {
        clientX = e.touches[0].clientX
        clientY = e.touches[0].clientY
      } else if ('clientX' in e) {
        clientX = e.clientX
        clientY = e.clientY
      }

      const rect = container.getBoundingClientRect()
      const x = ((clientX - rect.left) / rect.width) * 2 - 1
      const y = -(((clientY - rect.top) / rect.height) * 2 - 1)
      mouse.targetX = Math.max(-1, Math.min(1, x))
      mouse.targetY = Math.max(-1, Math.min(1, y))
    }

    window.addEventListener('mousemove', onPointerMove, { passive: true })
    window.addEventListener('touchmove', onPointerMove, { passive: true })

    // 6. Animation Loop
    let animationFrameId: number
    const clock = new THREE.Clock()

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate)
      const elapsed = clock.getElapsedTime()

      // Smooth mouse follow
      mouse.x += (mouse.targetX - mouse.x) * 0.05
      mouse.y += (mouse.targetY - mouse.y) * 0.05

      // Breathing + Idle Floating
      const breath = Math.sin(elapsed * 2.2) * 0.025
      const floatY = Math.sin(elapsed * 1.5) * 0.08
      creature.position.y = floatY

      bodyMesh.scale.set(1 + breath * 0.5, 1 - breath, 1 + breath * 0.5)

      // Creature head turns toward mouse
      creature.rotation.y = mouse.x * 0.35
      creature.rotation.x = -mouse.y * 0.25

      // Eyes look slightly ahead of head rotation
      eyeGroup.position.x = mouse.x * 0.08
      eyeGroup.position.y = 0.22 + mouse.y * 0.08

      // Ground shadow pulses gently with height
      shadowMesh.scale.setScalar(1 - floatY * 0.3)
      shadowMesh.material.opacity = 0.25 + floatY * 0.08

      renderer.render(scene, camera)
    }

    animate()

    // 7. Responsive Resize Handler
    const handleResize = () => {
      if (!container) return
      const newWidth = container.clientWidth
      const newHeight = container.clientHeight
      camera.aspect = newWidth / newHeight
      camera.updateProjectionMatrix()
      renderer.setSize(newWidth, newHeight)
    }

    const resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(container)

    return () => {
      cancelAnimationFrame(animationFrameId)
      window.removeEventListener('mousemove', onPointerMove)
      window.removeEventListener('touchmove', onPointerMove)
      resizeObserver.disconnect()
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
      renderer.dispose()
    }
  }, [interactive])

  if (!hasWebGL) {
    return (
      <div className={`relative flex items-center justify-center ${className}`}>
        {/* Graceful Fallback SVG Mascot */}
        <div className="w-56 h-72 bg-emerald-100/90 rounded-[50px] shadow-2xl flex flex-col items-center justify-center relative border border-emerald-200">
          <div className="flex gap-10 mb-2">
            <div className="w-4 h-4 bg-neutral-900 rounded-full relative">
              <div className="w-1.5 h-1.5 bg-white rounded-full absolute top-0.5 right-0.5" />
            </div>
            <div className="w-4 h-4 bg-neutral-900 rounded-full relative">
              <div className="w-1.5 h-1.5 bg-white rounded-full absolute top-0.5 right-0.5" />
            </div>
          </div>
          <div className="w-4 h-2 border-b-2 border-neutral-900 rounded-full" />
          <div className="absolute -bottom-4 w-44 h-4 bg-emerald-900/15 rounded-full blur-sm" />
        </div>
      </div>
    )
  }

  return (
    <div
      ref={mountRef}
      className={`relative w-full h-[400px] md:h-[480px] select-none pointer-events-auto ${className}`}
      aria-label="Portfolio Health Monitor 3D Autonomous AI Agent"
    />
  )
}


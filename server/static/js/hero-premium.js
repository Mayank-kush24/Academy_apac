/**
 * Premium Hero Section - Cinematic Glass Panel Animation
 * Apple-inspired motion design with natural easing and depth
 */

(function() {
    'use strict';

    const CONFIG = {
        panelCount: 6,
        radius: 420, // Large radius for wide cinematic arc
        centerX: 0, // Center offset X
        centerY: 0, // Center offset Y - no vertical offset
        startAngle: -55, // Starting angle in degrees (wider arc)
        endAngle: 55, // Ending angle in degrees
        targetRotation: 70, // Target rotation angle (degrees) - higher stop position
        overshootRotation: 78, // Overshoot angle for inertia effect - higher
        // Phased animation timing (smoother, more elegant)
        entryDuration: 800, // Entry phase (ms) - quick entry
        orbitDuration: 4000, // Orbit phase (ms) - smooth circular rotation
        overshootDuration: 500, // Overshoot phase (ms) - quick bounce
        settleDuration: 600, // Settle phase (ms) - smooth settle
        totalDuration: 5900, // Total animation duration
        floatAmplitude: 2.5, // Very subtle floating
        floatSpeed: 0.0006, // Very slow, elegant float
        parallaxIntensity: 0.25, // Strong parallax for depth
        depthRange: 120, // Large Z-axis depth range for physical slabs
        tiltAngle: 8, // Overall structure tilt in degrees
    };

    let container = null;
    let panels = [];
    let rotationStartTime = null;
    let floatOffset = 0;
    let animationFrameId = null;
    let currentRotation = 0;
    let isRotating = true;

    /**
     * Apple-style easing functions for cinematic motion
     */
    function easeOutCubic(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    function easeInOutCubic(t) {
        return t < 0.5
            ? 4 * t * t * t
            : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }

    /**
     * Ease-out-expo for smooth deceleration (Apple-like)
     */
    function easeOutExpo(t) {
        return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
    }

    /**
     * Ease-in-out-back for subtle bounce (entry phase)
     */
    function easeInOutBack(t) {
        const c1 = 1.70158;
        const c2 = c1 * 1.525;
        return t < 0.5
            ? (Math.pow(2 * t, 2) * ((c2 + 1) * 2 * t - c2)) / 2
            : (Math.pow(2 * t - 2, 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2;
    }

    /**
     * Ease-out-elastic for overshoot effect (inertia-based)
     */
    function easeOutElastic(t) {
        const c4 = (2 * Math.PI) / 3;
        return t === 0
            ? 0
            : t === 1
            ? 1
            : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1;
    }

    /**
     * Ease-in-out-quart for smooth settle
     */
    function easeInOutQuart(t) {
        return t < 0.5
            ? 8 * t * t * t * t
            : 1 - Math.pow(-2 * t + 2, 4) / 2;
    }

    /**
     * Interpolate between two RGB colors
     */
    function interpolateColor(color1, color2, t) {
        return {
            r: Math.round(color1.r + (color2.r - color1.r) * t),
            g: Math.round(color1.g + (color2.g - color1.g) * t),
            b: Math.round(color1.b + (color2.b - color1.b) * t)
        };
    }

    /**
     * Initialize the hero section
     */
    function init() {
        container = document.getElementById('glassPanelsContainer');
        if (!container) return;

        createPanels();
        rotationStartTime = performance.now();
        startAnimation();
        
        // Transition through animation phases
        setTimeout(() => {
            isRotating = false; // Enter idle float phase - pure circular stop
        }, CONFIG.totalDuration);
        
        // Apply overall structure tilt for 3D perspective (no vertical movement)
        if (container) {
            container.style.transform = `rotateX(${CONFIG.tiltAngle}deg)`;
        }
    }

    /**
     * Create glass panels
     */
    function createPanels() {
        const angleStep = (CONFIG.endAngle - CONFIG.startAngle) / (CONFIG.panelCount - 1);
        
        for (let i = 0; i < CONFIG.panelCount; i++) {
            const panel = document.createElement('div');
            panel.className = 'glass-panel';
            
            // Calculate initial position on arc
            const angle = CONFIG.startAngle + (angleStep * i);
            const radian = (angle * Math.PI) / 180;
            
            // Position along circular arc
            const x = CONFIG.centerX + CONFIG.radius * Math.cos(radian);
            const y = CONFIG.centerY + CONFIG.radius * Math.sin(radian);
            
            // Set initial transform with 3D - pure circular positioning
            panel.style.transform = `translate3d(${x}px, ${y}px, 0) rotate(${angle}deg)`;
            
            // Calculate depth for parallax and overlap FIRST (needed for hierarchy)
            // Center panels are closer (higher Z), edge panels are further
            const centerIndex = (CONFIG.panelCount - 1) / 2;
            const depthOffset = Math.abs(i - centerIndex);
            const maxDepth = centerIndex;
            const normalizedDepth = maxDepth > 0 ? depthOffset / maxDepth : 0;
            
            // Calculate gradient color based on position in arc (0 = left/orange, 1 = right/blue)
            // Smooth progression: Reddish-orange → Pink → Purple → Blue
            const normalizedPosition = i / (CONFIG.panelCount - 1); // 0 to 1
            
            // Interpolate colors based on position
            let gradientColor;
            let gradientIndex;
            
            if (normalizedPosition < 0.33) {
                // Left side: Reddish-orange to Pink
                const t = normalizedPosition / 0.33;
                gradientColor = interpolateColor(
                    {r: 255, g: 107, b: 53},   // Reddish-orange
                    {r: 233, g: 30, b: 99},    // Pink
                    t
                );
                gradientIndex = 0;
            } else if (normalizedPosition < 0.66) {
                // Middle: Pink to Purple
                const t = (normalizedPosition - 0.33) / 0.33;
                gradientColor = interpolateColor(
                    {r: 233, g: 30, b: 99},   // Pink
                    {r: 156, g: 39, b: 176},  // Purple
                    t
                );
                gradientIndex = 1;
            } else {
                // Right side: Purple to Blue
                const t = (normalizedPosition - 0.66) / 0.34;
                gradientColor = interpolateColor(
                    {r: 156, g: 39, b: 176},  // Purple
                    {r: 66, g: 133, b: 244},  // Blue
                    t
                );
                gradientIndex = 2;
            }
            
            // Store gradient color and apply directly to panel
            panel.setAttribute('data-gradient', gradientIndex);
            panel.setAttribute('data-gradient-position', normalizedPosition.toFixed(3));
            panel.setAttribute('data-gradient-r', gradientColor.r);
            panel.setAttribute('data-gradient-g', gradientColor.g);
            panel.setAttribute('data-gradient-b', gradientColor.b);
            
            // Apply gradient color to box-shadow via inline style (base panels)
            const gradientRgba = `rgba(${gradientColor.r}, ${gradientColor.g}, ${gradientColor.b}, `;
            panel.style.boxShadow = `
                0 0 0 3px ${gradientRgba}0.8),
                0 0 0 4px ${gradientRgba}0.65),
                0 0 0 5px ${gradientRgba}0.55),
                0 0 0 6px ${gradientRgba}0.45),
                0 0 0 7px ${gradientRgba}0.35),
                0 0 0 8px ${gradientRgba}0.25),
                0 16px 64px rgba(0, 0, 0, 0.25),
                0 6px 24px rgba(0, 0, 0, 0.15),
                inset 0 3px 12px rgba(255, 255, 255, 0.6),
                inset 0 -3px 12px rgba(0, 0, 0, 0.15),
                inset 0 1px 0 rgba(255, 255, 255, 0.8),
                inset 0 -1px 0 rgba(0, 0, 0, 0.2)
            `.replace(/\s+/g, ' ').trim();
            
            // Apply gradient color to ::before pseudo-element background
            const beforeBg = `
                radial-gradient(ellipse at 20% 30%, ${gradientRgba}0.35) 0%, transparent 65%),
                radial-gradient(ellipse at 80% 70%, ${gradientRgba}0.2) 0%, transparent 55%),
                linear-gradient(135deg, 
                    ${gradientRgba}0.25) 0%, 
                    ${gradientRgba}0.15) 50%, 
                    transparent 100%)
            `.replace(/\s+/g, ' ').trim();
            
            // Create a style element for this panel's ::before pseudo-element
            const styleId = `glass-panel-${i}-style`;
            let styleEl = document.getElementById(styleId);
            if (!styleEl) {
                styleEl = document.createElement('style');
                styleEl.id = styleId;
                document.head.appendChild(styleEl);
            }
            styleEl.textContent = `
                .glass-panel[data-gradient-position="${normalizedPosition.toFixed(3)}"]::before {
                    background: ${beforeBg};
                }
                .glass-panel[data-front="true"][data-gradient-position="${normalizedPosition.toFixed(3)}"]::before {
                    background: 
                        radial-gradient(ellipse at 20% 30%, ${gradientRgba}0.45) 0%, transparent 70%),
                        radial-gradient(ellipse at 80% 70%, ${gradientRgba}0.25) 0%, transparent 60%),
                        linear-gradient(135deg, 
                            ${gradientRgba}0.3) 0%, 
                            ${gradientRgba}0.2) 50%, 
                            transparent 100%);
                }
                .glass-panel[data-center="true"][data-gradient-position="${normalizedPosition.toFixed(3)}"]::before {
                    background: 
                        radial-gradient(ellipse at 20% 30%, ${gradientRgba}0.55) 0%, transparent 75%),
                        radial-gradient(ellipse at 80% 70%, ${gradientRgba}0.3) 0%, transparent 65%),
                        linear-gradient(135deg, 
                            ${gradientRgba}0.35) 0%, 
                            ${gradientRgba}0.25) 50%, 
                            transparent 100%);
                }
            `;
            
            // Store depth info for parallax and visual effects
            panel.setAttribute('data-depth', normalizedDepth.toFixed(3));
            
            // Store in panel data for animation
            const panelData = {
                element: panel,
                baseAngle: angle,
                index: i,
                depth: normalizedDepth
            };
            
            // No content - pure glass panels
            panel.innerHTML = '';
            
            // Z-index for proper layering (center panels on top)
            // Center panels should overlap edge panels
            const zIndexCenter = Math.floor(CONFIG.panelCount / 2);
            const distanceFromCenterForZ = Math.abs(i - zIndexCenter);
            panel.style.zIndex = CONFIG.panelCount - distanceFromCenterForZ;
            
            container.appendChild(panel);
            panels.push(panelData);
            
            // Much darker, more vibrant glass with hierarchy
            // Front panels: 0.5, back panels: 0.4 (much darker and more visible)
            const initialOpacity = 0.4 + (1 - normalizedDepth) * 0.1;
            panel.style.opacity = initialOpacity;
            
            // Add data attributes for visual hierarchy and update box-shadow accordingly
            // gradientRgba is already defined above, reuse it
            if (normalizedDepth === 0) {
                panel.setAttribute('data-center', 'true');
                // Update box-shadow for center panel with strongest colors
                panel.style.boxShadow = `
                    0 0 0 3px ${gradientRgba}1),
                    0 0 0 4px ${gradientRgba}0.85),
                    0 0 0 5px ${gradientRgba}0.75),
                    0 0 0 6px ${gradientRgba}0.65),
                    0 0 0 7px ${gradientRgba}0.55),
                    0 0 0 8px ${gradientRgba}0.45),
                    0 0 0 9px ${gradientRgba}0.35),
                    0 0 0 10px ${gradientRgba}0.25),
                    0 24px 96px rgba(0, 0, 0, 0.35),
                    0 10px 40px rgba(0, 0, 0, 0.25),
                    inset 0 5px 20px rgba(255, 255, 255, 0.8),
                    inset 0 -5px 20px rgba(0, 0, 0, 0.25),
                    inset 0 3px 0 rgba(255, 255, 255, 1),
                    inset 0 -3px 0 rgba(0, 0, 0, 0.3),
                    inset 0 0 30px rgba(255, 255, 255, 0.3)
                `.replace(/\s+/g, ' ').trim();
            } else if (normalizedDepth <= 0.3) {
                panel.setAttribute('data-front', 'true');
                // Update box-shadow for front panels with enhanced colors
                panel.style.boxShadow = `
                    0 0 0 3px ${gradientRgba}0.9),
                    0 0 0 4px ${gradientRgba}0.75),
                    0 0 0 5px ${gradientRgba}0.65),
                    0 0 0 6px ${gradientRgba}0.55),
                    0 0 0 7px ${gradientRgba}0.45),
                    0 0 0 8px ${gradientRgba}0.35),
                    0 0 0 9px ${gradientRgba}0.25),
                    0 20px 80px rgba(0, 0, 0, 0.3),
                    0 8px 32px rgba(0, 0, 0, 0.2),
                    inset 0 4px 16px rgba(255, 255, 255, 0.7),
                    inset 0 -4px 16px rgba(0, 0, 0, 0.2),
                    inset 0 2px 0 rgba(255, 255, 255, 0.9),
                    inset 0 -2px 0 rgba(0, 0, 0, 0.25)
                `.replace(/\s+/g, ' ').trim();
            }
            // Base panels keep the box-shadow set earlier
        }
    }

    /**
     * Get icon for panel (using Font Awesome icons)
     */
    function getPanelIcon(index) {
        const icons = [
            '<i class="fas fa-chart-line"></i>',
            '<i class="fas fa-search"></i>',
            '<i class="fas fa-chart-bar"></i>',
            '<i class="fas fa-bullseye"></i>',
            '<i class="fas fa-bolt"></i>',
            '<i class="fas fa-rocket"></i>'
        ];
        return icons[index % icons.length];
    }

    /**
     * Get text for panel
     */
    function getPanelText(index) {
        const texts = ['Analytics', 'Insights', 'Growth', 'Intelligence', 'Performance', 'Scale'];
        return texts[index % texts.length];
    }

    /**
     * Animate panels with premium cinematic motion
     */
    function animate() {
        if (!container) return;

        const currentTime = performance.now();
        floatOffset += CONFIG.floatSpeed;
        
        const elapsed = currentTime - rotationStartTime;
        
        // Phased animation: Entry → Orbit → Overshoot → Settle → Idle
        let entryProgress = 0;
        let orbitProgress = 0;
        let overshootProgress = 0;
        let settleProgress = 0;
        let rotationProgress = 0;
        
        if (isRotating && rotationStartTime) {
            const entryEnd = CONFIG.entryDuration;
            const orbitEnd = entryEnd + CONFIG.orbitDuration;
            const overshootEnd = orbitEnd + CONFIG.overshootDuration;
            const settleEnd = overshootEnd + CONFIG.settleDuration;
            
            // Entry phase: Panels fade in and scale up quickly
            if (elapsed < entryEnd) {
                entryProgress = easeInOutBack(elapsed / entryEnd);
            } else {
                entryProgress = 1;
            }
            
            // Orbit phase: Pure circular rotation motion
            if (elapsed >= entryEnd && elapsed < orbitEnd) {
                const orbitElapsed = elapsed - entryEnd;
                // Smooth ease-out for natural circular deceleration
                orbitProgress = easeOutCubic(orbitElapsed / CONFIG.orbitDuration);
            } else if (elapsed >= orbitEnd) {
                orbitProgress = 1;
            }
            
            // Overshoot phase: Inertia-based overshoot with bounce
            if (elapsed >= orbitEnd && elapsed < overshootEnd) {
                const overshootElapsed = elapsed - orbitEnd;
                overshootProgress = easeOutElastic(overshootElapsed / CONFIG.overshootDuration);
            } else if (elapsed >= overshootEnd) {
                overshootProgress = 1;
            }
            
            // Settle phase: Smooth settle to final position (no vertical movement)
            if (elapsed >= overshootEnd && elapsed < settleEnd) {
                const settleElapsed = elapsed - overshootEnd;
                settleProgress = easeInOutQuart(settleElapsed / CONFIG.settleDuration);
            } else if (elapsed >= settleEnd) {
                settleProgress = 1;
            }
            
            // Calculate rotation with overshoot - pure circular motion, no vertical lift
            const baseRotation = CONFIG.targetRotation;
            const overshootAmount = (CONFIG.overshootRotation - CONFIG.targetRotation) * overshootProgress;
            const settleAmount = -overshootAmount * (1 - settleProgress);
            currentRotation = baseRotation + overshootAmount + settleAmount;
            
            // Ensure smooth circular motion by using the rotation progress
            // This creates a perfect arc trajectory
        } else {
            // Idle phase: Gentle floating at final circular position
            entryProgress = 1;
            orbitProgress = 1;
            overshootProgress = 1;
            settleProgress = 1;
            currentRotation = CONFIG.targetRotation;
        }
        
        // Subtle floating motion (only when idle, not during rotation)
        const floatY = Math.sin(floatOffset) * CONFIG.floatAmplitude;
        const floatX = Math.cos(floatOffset * 0.8) * (CONFIG.floatAmplitude * 0.4);
        
        // No floating during rotation - pure circular motion only
        const floatIntensity = isRotating ? 0 : 1.0;
        
        panels.forEach((panelData) => {
            const { element, baseAngle, index, depth } = panelData;
            const currentAngle = baseAngle + currentRotation;
            const radian = (currentAngle * Math.PI) / 180;
            
            // Base position on circular arc - pure circular motion
            const baseX = CONFIG.centerX + CONFIG.radius * Math.cos(radian);
            const baseY = CONFIG.centerY + CONFIG.radius * Math.sin(radian);
            
            // Pure circular motion - no floating during rotation
            // Only add minimal floating when completely idle
            const x = baseX + (isRotating ? 0 : floatX * floatIntensity);
            const y = baseY + (isRotating ? 0 : floatY * floatIntensity);
            
            // Pure circular motion - no vertical lift or fade
            const finalY = y;
            
            // Enhanced 3D depth calculations for physical glass slabs
            const centerIndex = (CONFIG.panelCount - 1) / 2;
            const distanceFromCenter = index - centerIndex;
            
            // Z-axis depth: Heavy separation for physical slab appearance
            // Center at 0, edges at ±depthRange (larger separation)
            const translateZ = (distanceFromCenter / centerIndex) * CONFIG.depthRange;
            
            // Scale based on depth with entry animation
            // Front panels: 1.2x, back panels: 0.75x (larger variation)
            const baseScale = 0.75 + (1 - depth) * 0.45;
            const scale = baseScale * (0.2 + entryProgress * 0.8); // Entry scale animation
            
            // Enhanced parallax for depth perception (horizontal only, no vertical)
            const parallaxX = distanceFromCenter * CONFIG.parallaxIntensity * Math.sin(floatOffset * 0.5);
            const parallaxY = 0; // No vertical parallax - pure circular motion
            
            // 3D rotation transforms for physical glass slabs
            // RotateY: Edge panels tilt away from center (more pronounced)
            const rotateY = distanceFromCenter * 4; // Increased tilt for slab appearance
            
            // RotateX: Subtle vertical tilt based on position on arc (for 3D depth only)
            const rotateX = Math.sin(radian) * 3; // Subtle vertical perspective, not upward movement
            
            // Apply physical 3D transform for glass slabs
            element.style.transform = `
                translate3d(${x + parallaxX}px, ${finalY + parallaxY}px, ${translateZ}px)
                rotateX(${rotateX}deg)
                rotateY(${rotateY}deg)
                rotateZ(${currentAngle}deg)
                scale(${scale})
            `;
            
            // Much darker, more vibrant glass with visual hierarchy
            // Front panels: 0.5, back panels: 0.4 (much darker and more visible)
            const baseOpacity = 0.4 + (1 - depth) * 0.1;
            const opacity = baseOpacity * entryProgress; // Fade in during entry
            element.style.opacity = opacity;
        });

        animationFrameId = requestAnimationFrame(animate);
    }

    /**
     * Start animation loop
     */
    function startAnimation() {
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
        }
        animate();
    }

    /**
     * Handle window resize with smooth recalculation
     */
    function handleResize() {
        // Adjust radius based on viewport (maintain large cinematic arc)
        const viewportWidth = window.innerWidth;
        if (viewportWidth < 768) {
            CONFIG.radius = 200;
        } else if (viewportWidth < 1200) {
            CONFIG.radius = 320;
        } else {
            CONFIG.radius = 420;
        }
        
        // Recalculate panel positions if already created
        // This will be handled naturally in the next animation frame
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Handle resize
    window.addEventListener('resize', handleResize);
    handleResize();

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
        }
    });
})();

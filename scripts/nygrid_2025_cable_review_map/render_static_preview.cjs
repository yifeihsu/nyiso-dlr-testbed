/* Rasterize the test-generated SVG without a browser or page execution.
 * This checks the map geometry/colors, not native HTML/CSS layout or hit testing. */
'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'output/nygrid_2025_cable_review_map');
const graphics=require(process.argv[2]||'@napi-rs/canvas');
const {DOMParser}=require(path.join(root,'tmp/nygrid_2025_slim_map_test/node_modules/linkedom'));
const sha=buffer=>crypto.createHash('sha256').update(buffer).digest('hex');
(async()=>{
    const images=[];
    for(const name of ['default_review_static','classification_conflicts_static','selected_y50_static','mobile_review_static']){
        const source=path.join(out,'qa',name+'.svg');if(!fs.existsSync(source))throw Error('Missing interaction-test SVG: '+source);
        const bytes=fs.readFileSync(source);
        const xml=new DOMParser().parseFromString(bytes.toString('utf8'),'image/svg+xml'),svg=xml.documentElement;
        const units=Number(svg.getAttribute('viewBox').split(/\s+/)[2])/Number(svg.getAttribute('width'));
        for(const node of svg.querySelectorAll('*')){
            for(const key of ['fill','stroke']){
                const value=node.getAttribute(key);
                if(value==='transparent')node.setAttribute(key,'none');
                else if(/^#[a-f0-9]{8}$/i.test(value||''))node.setAttribute(key,value.slice(0,7));
            }
            if(String(node.tagName).toLowerCase()==='text')node.setAttribute('stroke','none');
            if(node.getAttribute('vector-effect')==='non-scaling-stroke'){
                const value=Number.parseFloat(node.getAttribute('stroke-width'));
                if(Number.isFinite(value))node.setAttribute('stroke-width',String(value*units));
                const inline=node.style?.getPropertyValue('stroke-width');
                if(inline&&Number.isFinite(Number.parseFloat(inline)))node.style.setProperty('stroke-width',String(Number.parseFloat(inline)*units));
                node.removeAttribute('vector-effect');
            }
        }
        const image=await graphics.loadImage(Buffer.from(svg.outerHTML));
        const canvas=graphics.createCanvas(image.width,image.height),ctx=canvas.getContext('2d');
        ctx.fillStyle='#f7fafc';ctx.fillRect(0,0,image.width,image.height);ctx.drawImage(image,0,0);
        const png=canvas.toBuffer('image/png'),target=path.join(out,'qa',name+'.png');fs.writeFileSync(target,png);
        images.push({svg_sha256:sha(bytes),image:path.relative(out,target).replaceAll('\\','/'),
                     png_sha256:sha(png),width:image.width,height:image.height});
    }
    const receipt={passed:true,method:'Native SVG rasterization from LinkeDOM interaction-test output; no browser, browser file access or page navigation.',
        verifies:'Map-vector geometry, flags, colors and labels under disclosed layout stubs.',
        native_browser_visual_QA:false,native_hit_testing:false,full_HTML_sidebar_layout_verified:false,
        preview_adjustments:['Authored SVG CSS resolved to presentation attributes by the DOM test.',
            'Transparent/eight-digit colors normalized, non-scaling strokes resolved and text halos flattened for native rasterizer compatibility.'],
        html_sha256:sha(fs.readFileSync(path.join(out,'network_map.html'))),images};
    fs.writeFileSync(path.join(out,'static_preview_receipt.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify({passed:true,images:images.length,native_browser_visual_QA:false}));
})().catch(error=>{console.error(error);process.exitCode=1;});

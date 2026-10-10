"""Two parameter-comparable backbones, no stochastic layers or mutable batch statistics."""
import torch
from torch import nn

class ResidualBlock(nn.Module):
    def __init__(self,cin,cout,stride=1):
        super().__init__()
        self.conv1=nn.Conv2d(cin,cout,3,stride=stride,padding=1,bias=False);self.gn1=nn.GroupNorm(8,cout)
        self.conv2=nn.Conv2d(cout,cout,3,padding=1,bias=False);self.gn2=nn.GroupNorm(8,cout)
        self.skip=nn.Identity() if cin==cout and stride==1 else nn.Sequential(nn.Conv2d(cin,cout,1,stride=stride,bias=False),nn.GroupNorm(8,cout))
    def forward(self,x):
        y=torch.nn.functional.silu(self.gn1(self.conv1(x)));y=self.gn2(self.conv2(y))
        return torch.nn.functional.silu(y+self.skip(x))

class ResNet18GN(nn.Module):
    def __init__(self,classes,width=32):
        super().__init__();self.stem=nn.Sequential(nn.Conv2d(3,width,3,padding=1,bias=False),nn.GroupNorm(8,width),nn.SiLU())
        layers=[];cin=width
        for j,cout in enumerate((width,width*2,width*4,width*8)):
            layers.extend([ResidualBlock(cin,cout,1 if j==0 else 2),ResidualBlock(cout,cout)]);cin=cout
        self.blocks=nn.Sequential(*layers);self.head=nn.Linear(cin,classes)
    def forward(self,x):return self.head(self.blocks(self.stem(x)).mean((2,3)))

class AttentionBlock(nn.Module):
    def __init__(self,dim=192,heads=3,ratio=3):
        super().__init__();self.heads=heads;self.dim=dim;self.ln1=nn.LayerNorm(dim);self.qkv=nn.Linear(dim,dim*3)
        self.out=nn.Linear(dim,dim);self.ln2=nn.LayerNorm(dim);self.mlp=nn.Sequential(nn.Linear(dim,dim*ratio),nn.GELU(),nn.Linear(dim*ratio,dim))
    def forward(self,x):
        b,n,d=x.shape;qkv=self.qkv(self.ln1(x)).reshape(b,n,3,self.heads,d//self.heads).permute(2,0,3,1,4)
        q,k,v=qkv.unbind(0);p=((q@k.transpose(-1,-2))*(d//self.heads)**-.5).softmax(-1)
        y=(p@v).transpose(1,2).reshape(b,n,d);x=x+self.out(y)
        return x+self.mlp(self.ln2(x))

class ViTSmall(nn.Module):
    def __init__(self,classes,dim=192,depth=6,heads=3):
        super().__init__();self.patch=nn.Conv2d(3,dim,4,stride=4);self.cls=nn.Parameter(torch.zeros(1,1,dim))
        self.position=nn.Parameter(torch.empty(1,65,dim));nn.init.normal_(self.position,std=.02)
        self.blocks=nn.Sequential(*[AttentionBlock(dim,heads,3) for _ in range(depth)])
        self.norm=nn.LayerNorm(dim);self.head=nn.Linear(dim,classes)
    def forward(self,x):
        x=self.patch(x).flatten(2).transpose(1,2);x=torch.cat([self.cls.expand(len(x),-1,-1),x],1)+self.position
        return self.head(self.norm(self.blocks(x))[:,0])

def build(architecture,classes):
    if architecture=='ResNet18GN':return ResNet18GN(classes)
    if architecture=='ViTSmall':return ViTSmall(classes)
    raise ValueError(architecture)

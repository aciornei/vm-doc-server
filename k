config vdom
    edit INTRANET
        config firewall address
            edit "DTI-ANSIBLE-01"
                show full-configuration
            next
        end
    next
end
